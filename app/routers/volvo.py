from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
import math
import urllib.error
import urllib.request
import uuid

from fastapi import APIRouter, Depends, Request, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.db import get_db
from app.auth import get_user, require, csrf
from app.models import Equipment, Location
from app.volvo_models import VolvoVehicle, VolvoMapping, VolvoAudit, VolvoSync, VolvoReport, VolvoLocationZone
from app.services.volvo_store import latest_reports
from app.services.volvo_client import timestamp

router = APIRouter(prefix='/api/volvo', tags=['Volvo'])
IST = timezone(timedelta(hours=5, minutes=30))
VALID_SHIFTS = {'ALL', 'A', 'B', 'C'}


def _ensure_location_zone_table(db):
    VolvoLocationZone.__table__.create(bind=db.get_bind(), checkfirst=True)


def _location_zones(db):
    _ensure_location_zone_table(db)
    zones=[]
    for zone, loc in db.execute(
        select(VolvoLocationZone, Location)
        .join(Location, Location.location_id == VolvoLocationZone.location_id)
        .where(Location.active.is_(True))
        .order_by(Location.location_name, Location.location_id)
    ).all():
        zones.append({
            'location_id': loc.location_id,
            'location_name': loc.location_name,
            'location_type': loc.location_type,
            'latitude': float(zone.latitude),
            'longitude': float(zone.longitude),
            'radius_m': float(zone.radius_m),
        })
    return zones


def _assign_location(row, zones):
    gps=row.get('gps') or {}
    try:
        lat=float(gps.get('latitude'))
        lon=float(gps.get('longitude'))
    except (TypeError, ValueError):
        row['location_id']=None
        row['location_name']='GPS unavailable'
        row['location_distance_m']=None
        return row
    best=None
    for zone in zones:
        km=_haversine_km(
            {'latitude':lat,'longitude':lon},
            {'latitude':zone['latitude'],'longitude':zone['longitude']},
        )
        metres=km*1000.0
        if metres <= zone['radius_m'] and (best is None or metres < best[0]):
            best=(metres,zone)
    if best:
        metres,zone=best
        row['location_id']=zone['location_id']
        row['location_name']=zone['location_name']
        row['location_distance_m']=round(metres,1)
    else:
        row['location_id']=None
        row['location_name']='Transit / outside zones'
        row['location_distance_m']=None
    return row


def _num(value):
    try:
        if value is None or value == '':
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _find_key(value, key):
    """Find an exact JSON key recursively without assuming a specific rFMS nesting version."""
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find_key(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_key(child, key)
            if found is not None:
                return found
    return None


def _driver(value):
    if not isinstance(value, dict):
        return str(value) if value else None
    tacho = value.get('tachoDriverIdentification') or {}
    if isinstance(tacho, dict) and tacho.get('driverIdentification'):
        return str(tacho['driverIdentification'])
    oem = value.get('oemDriverIdentification') or {}
    if isinstance(oem, dict) and oem.get('oemDriverIdentification'):
        return str(oem['oemDriverIdentification'])
    return None


def _pto_totals(accumulated):
    seconds = 0.0
    fuel_ml = 0.0
    rows = accumulated.get('ptoActiveClass') if isinstance(accumulated, dict) else None
    if not isinstance(rows, list):
        return None, None
    any_seconds = any_fuel = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        s = _num(row.get('seconds') if 'seconds' in row else row.get('durationS'))
        f = _num(row.get('milliLitres') if 'milliLitres' in row else row.get('fuelConsumptionMl'))
        if s is not None:
            seconds += s
            any_seconds = True
        if f is not None:
            fuel_ml += f
            any_fuel = True
    return (seconds if any_seconds else None), (fuel_ml if any_fuel else None)


def _axle_values(payload):
    rows = _find_key(payload, 'vehicleAxles')
    if not isinstance(rows, list):
        return [], None
    out = []
    total = 0.0
    any_load = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        position = row.get('vehicleAxlePosition') or row.get('position')
        load = _num(row.get('vehicleAxleLoad') if 'vehicleAxleLoad' in row else row.get('loadKg'))
        if load is not None:
            total += load
            any_load = True
        out.append({'position': position, 'load_kg': load})
    return out, (total if any_load else None)


def _active_telltales(payload):
    info = _find_key(payload, 'tellTaleInfo')
    if isinstance(info, dict):
        info = [info]
    if not isinstance(info, list):
        return []
    active = []
    inactive = {'OFF', 'INACTIVE', 'OK', 'NORMAL', 'FALSE', '0', 'NOT_AVAILABLE', 'NOT AVAILABLE', 'UNAVAILABLE', ''}
    for row in info:
        if not isinstance(row, dict):
            continue
        name = row.get('telltale') or row.get('tellTale') or row.get('name') or row.get('id')
        state = row.get('state') or row.get('status') or row.get('value')
        if name and str(state if state is not None else '').strip().upper() not in inactive:
            active.append({'name': str(name), 'state': str(state) if state is not None else 'ACTIVE'})
    return active[:20]


def _status_values(payload):
    payload = payload or {}
    snapshot = payload.get('snapshotData') or {}
    accumulated = payload.get('accumulatedData') or {}
    uptime = payload.get('uptimeData') or {}
    gps = snapshot.get('gnssPosition') if isinstance(snapshot, dict) else None
    if not isinstance(gps, dict):
        found = _find_key(payload, 'gnssPosition')
        gps = found if isinstance(found, dict) else None
    pto_seconds, pto_fuel_ml = _pto_totals(accumulated)
    axles, axle_total_kg = _axle_values(payload)
    idle_fuel = None
    moving_fuel = None
    if isinstance(accumulated, dict):
        idle_fuel = _num(accumulated.get('fuelDuringWheelbaseSpeedZero'))
        if idle_fuel is None:
            idle_fuel = _num(accumulated.get('fuelWheelbaseSpeedZero'))
        moving_fuel = _num(accumulated.get('fuelWheelbaseSpeedOverZero'))
    telltales = _active_telltales(payload)
    return {
        'reported_at': payload.get('receivedDateTime') or payload.get('createdDateTime'),
        'engine_hours': _num(payload.get('totalEngineHours')),
        'distance_m': _num(payload.get('hrTotalVehicleDistance')),
        'fuel_ml': _num(payload.get('engineTotalFuelUsed')),
        'gross_weight_kg': _num(payload.get('grossCombinationVehicleWeight')),
        'fuel_level_pct': _num(snapshot.get('fuelLevel1')) if isinstance(snapshot, dict) else None,
        'adblue_pct': _num(snapshot.get('catalystFuelLevel')) if isinstance(snapshot, dict) else None,
        'engine_speed_rpm': _num(snapshot.get('engineSpeed')) if isinstance(snapshot, dict) else None,
        'wheel_speed_kmh': _num(snapshot.get('wheelBasedSpeed')) if isinstance(snapshot, dict) else None,
        'ambient_temp_c': _num(snapshot.get('ambientAirTemperature')) if isinstance(snapshot, dict) else None,
        'driver_working_state': snapshot.get('driver1WorkingState') if isinstance(snapshot, dict) else None,
        'moving_seconds': _num(accumulated.get('durationWheelbaseSpeedOverZero')) if isinstance(accumulated, dict) else None,
        'stationary_seconds': _num(accumulated.get('durationWheelbaseSpeedZero')) if isinstance(accumulated, dict) else None,
        'idle_fuel_ml': idle_fuel,
        'moving_fuel_ml': moving_fuel,
        'pto_seconds': pto_seconds,
        'pto_fuel_ml': pto_fuel_ml,
        'driver_id': _driver(payload.get('driver1Id')),
        'service_distance_m': _num(uptime.get('serviceDistance')) if isinstance(uptime, dict) else _num(_find_key(payload, 'serviceDistance')),
        'coolant_temp_c': _num(uptime.get('engineCoolantTemperature')) if isinstance(uptime, dict) else _num(_find_key(payload, 'engineCoolantTemperature')),
        'brake_pressure1_pa': _num(uptime.get('serviceBrakeAirPressureCircuit1')) if isinstance(uptime, dict) else _num(_find_key(payload, 'serviceBrakeAirPressureCircuit1')),
        'brake_pressure2_pa': _num(uptime.get('serviceBrakeAirPressureCircuit2')) if isinstance(uptime, dict) else _num(_find_key(payload, 'serviceBrakeAirPressureCircuit2')),
        'estimated_distance_to_empty_m': _num(_find_key(payload, 'estimatedDistanceToEmpty')),
        'axles': axles,
        'axle_total_kg': axle_total_kg,
        'active_telltales': telltales,
        'gps': gps,
    }


def _position_values(payload):
    payload = payload or {}
    gps = payload.get('gnssPosition') or {}
    return {
        'reported_at': payload.get('receivedDateTime') or payload.get('createdDateTime') or gps.get('positionDateTime'),
        'gps': gps if isinstance(gps, dict) else None,
        'wheel_speed_kmh': _num(payload.get('wheelBasedSpeed')),
        'gps_speed_kmh': _num(gps.get('speed')) if isinstance(gps, dict) else None,
        'heading': _num(gps.get('heading')) if isinstance(gps, dict) else None,
        'altitude_m': _num(gps.get('altitude')) if isinstance(gps, dict) else None,
    }


def _gps_candidate(payload):
    values = _position_values(payload)
    gps = values['gps']
    when = timestamp((gps or {}).get('positionDateTime')) or timestamp(values['reported_at'])
    return gps, when


def _status_activity_delta(current_payload, previous_payload):
    if not previous_payload:
        return False
    cur = _status_values(current_payload)
    prev = _status_values(previous_payload)
    cur_when = timestamp(cur['reported_at'])
    prev_when = timestamp(prev['reported_at'])
    if cur_when and prev_when:
        gap = (cur_when - prev_when).total_seconds()
        if gap <= 0 or gap > 3 * 3600:
            return False
    distance_delta = None
    if cur['distance_m'] is not None and prev['distance_m'] is not None and cur['distance_m'] >= prev['distance_m']:
        distance_delta = cur['distance_m'] - prev['distance_m']
    engine_delta = None
    if cur['engine_hours'] is not None and prev['engine_hours'] is not None and cur['engine_hours'] >= prev['engine_hours']:
        engine_delta = cur['engine_hours'] - prev['engine_hours']
    fuel_delta = None
    if cur['fuel_ml'] is not None and prev['fuel_ml'] is not None and cur['fuel_ml'] >= prev['fuel_ml']:
        fuel_delta = cur['fuel_ml'] - prev['fuel_ml']
    nearly_stationary = distance_delta is None or distance_delta < 50
    return nearly_stationary and ((engine_delta is not None and engine_delta > 0.001) or (fuel_delta is not None and fuel_delta > 0))


def _state(status_payload, position_payload, server_time, previous_status=None, offline_minutes=120):
    s = _status_values(status_payload)
    p = _position_values(position_payload)
    reported = max(
        [x for x in (timestamp(s['reported_at']), timestamp(p['reported_at'])) if x],
        default=None,
    )
    if reported and (server_time - reported).total_seconds() > offline_minutes * 60:
        return 'OFFLINE'
    speeds = [x for x in (p['wheel_speed_kmh'], p['gps_speed_kmh'], s['wheel_speed_kmh']) if x is not None]
    if speeds and max(speeds) > 1:
        return 'RUNNING'
    if s['engine_speed_rpm'] is not None and s['engine_speed_rpm'] > 0:
        return 'IDLE'
    if _status_activity_delta(status_payload, previous_status):
        return 'IDLE'
    return 'STOPPED'


def _latest_payloads(db):
    out = defaultdict(dict)
    for report in latest_reports(db):
        out[report.vin][report.kind] = report.payload or {}
    return out


def _recent_status_pairs(db, max_rows=None):
    """Latest two status payloads per VIN for IDLE inference.

    Uses a window query so live refresh reads about two rows per truck rather
    than a fixed block of hundreds of JSON payloads.
    """
    result = defaultdict(list)
    ranked = (
        select(
            VolvoReport.vin.label('vin'),
            VolvoReport.payload.label('payload'),
            func.row_number().over(
                partition_by=VolvoReport.vin,
                order_by=(VolvoReport.created_at.desc(), VolvoReport.fetched_at.desc()),
            ).label('rn'),
        )
        .where(VolvoReport.kind == 'vehiclestatuses')
        .subquery()
    )
    rows = db.execute(
        select(ranked.c.vin, ranked.c.payload)
        .where(ranked.c.rn <= 2)
        .order_by(ranked.c.vin, ranked.c.rn)
    ).all()
    for vin, payload in rows:
        result[vin].append(payload or {})
    return result


def _current_shift_window(now_utc):
    """Return current TIOM operating shift and its UTC start time."""
    local = now_utc.astimezone(IST)
    clock = local.time().replace(tzinfo=None)
    if time(hour=6) <= clock < time(hour=14):
        shift = 'A'
        start_local = datetime.combine(local.date(), time(hour=6), IST)
    elif time(hour=14) <= clock < time(hour=22):
        shift = 'B'
        start_local = datetime.combine(local.date(), time(hour=14), IST)
    else:
        shift = 'C'
        shift_date = local.date() if clock >= time(hour=22) else local.date() - timedelta(days=1)
        start_local = datetime.combine(shift_date, time(hour=22), IST)
    return shift, start_local.astimezone(timezone.utc)


def _shift_operational_vins(db, now_utc):
    """Vehicles that have demonstrated real activity during the current shift.

    'Operational' is intentionally different from instantaneous movement:
    a haul truck remains operational while briefly stopped for loading,
    weighing or unloading if it has moved / run its engine during this shift.
    """
    shift, start_utc = _current_shift_window(now_utc)
    reports = db.scalars(
        select(VolvoReport)
        .where(
            VolvoReport.kind.in_(['vehiclestatuses', 'vehiclepositions']),
            VolvoReport.created_at >= start_utc,
            VolvoReport.created_at <= now_utc,
        )
        .order_by(VolvoReport.vin, VolvoReport.created_at)
    ).all()

    active = set()
    counters = defaultdict(lambda: {'engine': None, 'distance': None, 'fuel': None})
    for report in reports:
        payload = report.payload or {}
        if report.kind == 'vehiclepositions':
            p = _position_values(payload)
            speeds = [x for x in (p['wheel_speed_kmh'], p['gps_speed_kmh']) if x is not None]
            if speeds and max(speeds) > 1:
                active.add(report.vin)
            continue

        s = _status_values(payload)
        speeds = [x for x in (s['wheel_speed_kmh'],) if x is not None]
        driver_state = str(s.get('driver_working_state') or '').strip().upper()
        if (speeds and max(speeds) > 1) or (s['engine_speed_rpm'] is not None and s['engine_speed_rpm'] > 0):
            active.add(report.vin)
        if driver_state in {'DRIVE', 'DRIVING', 'WORK', 'WORKING'}:
            active.add(report.vin)

        previous = counters[report.vin]
        current_values = {
            'engine': s['engine_hours'],
            'distance': s['distance_m'],
            'fuel': s['fuel_ml'],
        }
        for key, current_value in current_values.items():
            previous_value = previous[key]
            if current_value is not None and previous_value is not None and current_value > previous_value:
                active.add(report.vin)
            if current_value is not None:
                previous[key] = current_value

    return active, shift, start_utc


def _period_bounds(from_date, to_date):
    # Query wide enough to include C shift after midnight on the final operating date.
    start_local = datetime.combine(from_date, time.min, IST)
    end_local = datetime.combine(to_date + timedelta(days=1), time(hour=6), IST)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _operating_date_shift(when):
    if when is None:
        return None, None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    local = when.astimezone(IST)
    clock = local.time().replace(tzinfo=None)
    if clock < time(hour=6):
        return local.date() - timedelta(days=1), 'C'
    if clock < time(hour=14):
        return local.date(), 'A'
    if clock < time(hour=22):
        return local.date(), 'B'
    return local.date(), 'C'


def _in_operating_range(when, from_date, to_date, shift='ALL'):
    op_date, op_shift = _operating_date_shift(when)
    if op_date is None or op_date < from_date or op_date > to_date:
        return False
    return shift == 'ALL' or op_shift == shift


def _positive_deltas(points, index):
    total = 0.0
    prev = None
    for point in points:
        value = point[index]
        if value is None:
            continue
        if prev is not None and value >= prev:
            total += value - prev
        prev = value
    return total


def _counter_delta(current, previous):
    if current is None or previous is None or current < previous:
        return 0.0
    return current - previous


def _period_metrics(status_reports, mappings, labels, allowed_vins, from_date, to_date, shift='ALL'):
    """Calculate counter deltas across reading boundaries.

    Each interval is credited to the operating date/shift of the *later* reading.
    This preserves deltas when a sparse telemetry interval crosses a shift or day
    boundary instead of resetting the counter comparison at every group.
    """
    by_vin = defaultdict(list)
    by_day = defaultdict(lambda: {
        'fuel_l': 0.0, 'distance_km': 0.0, 'engine_h': 0.0,
        'idle_fuel_l': 0.0, 'moving_fuel_l': 0.0,
    })
    for report in status_reports:
        if report.vin not in allowed_vins:
            continue
        v = _status_values(report.payload)
        when = timestamp(v['reported_at']) or report.created_at
        if when and when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when is None:
            continue
        by_vin[report.vin].append(
            (when, v['engine_hours'], v['distance_m'], v['fuel_ml'], v['idle_fuel_ml'], v['moving_fuel_ml'])
        )

    vehicle_totals = defaultdict(lambda: {
        'engine_h': 0.0, 'distance_km': 0.0, 'fuel_l': 0.0,
        'idle_fuel_l': 0.0, 'moving_fuel_l': 0.0,
    })
    for vin, points in by_vin.items():
        points.sort(key=lambda x: x[0])
        previous = None
        for current in points:
            if previous is None:
                previous = current
                continue
            when = current[0]
            # Credit the full interval to the later reading's operating bucket.
            if _in_operating_range(when, from_date, to_date, shift):
                op_date, _op_shift = _operating_date_shift(when)
                values = {
                    'engine_h': _counter_delta(current[1], previous[1]),
                    'distance_km': _counter_delta(current[2], previous[2]) / 1000.0,
                    'fuel_l': _counter_delta(current[3], previous[3]) / 1000.0,
                    'idle_fuel_l': _counter_delta(current[4], previous[4]) / 1000.0,
                    'moving_fuel_l': _counter_delta(current[5], previous[5]) / 1000.0,
                }
                day = op_date.isoformat()
                for key, value in values.items():
                    vehicle_totals[vin][key] += value
                    by_day[day][key] += value
            previous = current

    vehicles = []
    for vin, values in vehicle_totals.items():
        label = labels.get(vin) or mappings.get(vin) or vin[-6:]
        engine_h = values['engine_h']
        distance_km = values['distance_km']
        fuel_l = values['fuel_l']
        vehicles.append({
            'vin': vin,
            'machine_id': mappings.get(vin),
            'label': label,
            'engine_h': round(engine_h, 2),
            'distance_km': round(distance_km, 2),
            'fuel_l': round(fuel_l, 2),
            'idle_fuel_l': round(values['idle_fuel_l'], 2),
            'moving_fuel_l': round(values['moving_fuel_l'], 2),
            'fuel_lph': round(fuel_l / engine_h, 2) if engine_h > 0 else None,
            'fuel_l_100km': round((fuel_l / distance_km) * 100, 2) if distance_km > 0 else None,
        })
    vehicles.sort(key=lambda x: (x['machine_id'] is None, x['label']))

    daily = []
    for day in sorted(by_day):
        values = by_day[day]
        daily.append({
            'date': day,
            'engine_h': round(values['engine_h'], 2),
            'distance_km': round(values['distance_km'], 2),
            'fuel_l': round(values['fuel_l'], 2),
            'idle_fuel_l': round(values['idle_fuel_l'], 2),
            'moving_fuel_l': round(values['moving_fuel_l'], 2),
        })
    totals = {
        'engine_h': round(sum(x['engine_h'] for x in vehicles), 2),
        'distance_km': round(sum(x['distance_km'] for x in vehicles), 2),
        'fuel_l': round(sum(x['fuel_l'] for x in vehicles), 2),
        'idle_fuel_l': round(sum(x['idle_fuel_l'] for x in vehicles), 2),
        'moving_fuel_l': round(sum(x['moving_fuel_l'] for x in vehicles), 2),
    }
    totals['fuel_lph'] = round(totals['fuel_l'] / totals['engine_h'], 2) if totals['engine_h'] > 0 else None
    totals['fuel_l_100km'] = round((totals['fuel_l'] / totals['distance_km']) * 100, 2) if totals['distance_km'] > 0 else None
    return vehicles, daily, totals


def _fleet_row(vehicle, mappings, reports, recent_statuses, now, operational_vins=None):
    status = reports[vehicle.vin].get('vehiclestatuses', {})
    position = reports[vehicle.vin].get('vehiclepositions', {})
    previous = recent_statuses.get(vehicle.vin, [None, None])
    previous_status = previous[1] if len(previous) > 1 else None
    sv = _status_values(status)
    pv = _position_values(position)
    candidates = []
    pgps, pwhen = _gps_candidate(position)
    if pgps and pwhen:
        candidates.append((pwhen, pgps))
    sgps = sv['gps']
    swhen = timestamp((sgps or {}).get('positionDateTime')) or timestamp(sv['reported_at'])
    if sgps and swhen:
        candidates.append((swhen, sgps))
    gps = max(candidates, key=lambda x: x[0])[1] if candidates else None
    mapped_id = mappings.get(vehicle.vin)
    name = vehicle.payload.get('customerVehicleName') or vehicle.payload.get('vehicleName') or vehicle.vin[-6:]
    reported_candidates = [x for x in (timestamp(sv['reported_at']), timestamp(pv['reported_at'])) if x]
    latest_at = max(reported_candidates) if reported_candidates else None
    age_seconds = max(0, int((now - latest_at).total_seconds())) if latest_at else None
    return {
        'vin': vehicle.vin,
        'name': name,
        'brand': vehicle.payload.get('brand'),
        'model': vehicle.payload.get('model'),
        'machine_id': mapped_id,
        'state': _state(status, position, now, previous_status),
        'operational': vehicle.vin in (operational_vins or set()),
        'engine_hours': sv['engine_hours'],
        'distance_km': round(sv['distance_m'] / 1000.0, 2) if sv['distance_m'] is not None else None,
        'fuel_used_l': round(sv['fuel_ml'] / 1000.0, 2) if sv['fuel_ml'] is not None else None,
        'fuel_level_pct': sv['fuel_level_pct'],
        'adblue_pct': sv['adblue_pct'],
        'engine_speed_rpm': sv['engine_speed_rpm'],
        'wheel_speed_kmh': pv['wheel_speed_kmh'] if pv['wheel_speed_kmh'] is not None else sv['wheel_speed_kmh'],
        'gps_speed_kmh': pv['gps_speed_kmh'],
        'heading': pv['heading'] if pv['heading'] is not None else _num((gps or {}).get('heading')),
        'altitude_m': pv['altitude_m'] if pv['altitude_m'] is not None else _num((gps or {}).get('altitude')),
        'driver_id': sv['driver_id'],
        'driver_working_state': sv['driver_working_state'],
        'moving_h': round(sv['moving_seconds'] / 3600.0, 2) if sv['moving_seconds'] is not None else None,
        'stationary_h': round(sv['stationary_seconds'] / 3600.0, 2) if sv['stationary_seconds'] is not None else None,
        'idle_fuel_l': round(sv['idle_fuel_ml'] / 1000.0, 2) if sv['idle_fuel_ml'] is not None else None,
        'moving_fuel_l': round(sv['moving_fuel_ml'] / 1000.0, 2) if sv['moving_fuel_ml'] is not None else None,
        'pto_h': round(sv['pto_seconds'] / 3600.0, 2) if sv['pto_seconds'] is not None else None,
        'pto_fuel_l': round(sv['pto_fuel_ml'] / 1000.0, 2) if sv['pto_fuel_ml'] is not None else None,
        'gross_weight_kg': sv['gross_weight_kg'],
        'axle_total_kg': sv['axle_total_kg'],
        'axles': sv['axles'],
        'service_distance_km': round(sv['service_distance_m'] / 1000.0, 1) if sv['service_distance_m'] is not None else None,
        'coolant_temp_c': sv['coolant_temp_c'],
        'brake_pressure1_kpa': round(sv['brake_pressure1_pa'] / 1000.0, 1) if sv['brake_pressure1_pa'] is not None else None,
        'brake_pressure2_kpa': round(sv['brake_pressure2_pa'] / 1000.0, 1) if sv['brake_pressure2_pa'] is not None else None,
        'estimated_distance_to_empty_km': round(sv['estimated_distance_to_empty_m'] / 1000.0, 1) if sv['estimated_distance_to_empty_m'] is not None else None,
        'ambient_temp_c': sv['ambient_temp_c'],
        'active_telltales': sv['active_telltales'],
        'warning_count': len(sv['active_telltales']),
        'reported_at': latest_at or sv['reported_at'] or pv['reported_at'],
        'telemetry_age_seconds': age_seconds,
        'gps': gps,
    }


@router.get('/fleet')
def fleet(request: Request, db=Depends(get_db)):
    user = get_user(db, request)
    require(user, module='DASHBOARD')
    reports = _latest_payloads(db)
    mappings = {r.vin: r.machine_id for r in db.scalars(select(VolvoMapping))}
    recent_statuses = _recent_status_pairs(db)
    sync = db.scalar(select(VolvoSync).order_by(VolvoSync.completed_at.desc()).limit(1))
    now = datetime.now(timezone.utc)
    operational_vins, current_shift, shift_started_at = _shift_operational_vins(db, now)
    zones = _location_zones(db)
    rows = [
        _assign_location(_fleet_row(vehicle, mappings, reports, recent_statuses, now, operational_vins), zones)
        for vehicle in db.scalars(select(VolvoVehicle).order_by(VolvoVehicle.vin))
    ]
    equipment = [
        {'id': e.machine_id, 'label': e.door_no or e.vehicle_no or e.machine_id}
        for e in db.scalars(select(Equipment).where(Equipment.active.is_(True)).order_by(Equipment.machine_id))
    ] if user.admin else []
    return {
        'rows': rows,
        'equipment': equipment,
        'can_map': user.admin,
        'last_sync': sync.completed_at if sync else None,
        'counts': sync.counts if sync else {},
        'server_time': now,
        'current_shift': current_shift,
        'shift_started_at': shift_started_at,
        'operational_count': sum(1 for row in rows if row['operational']),
        'location_zones': zones,
    }


@router.get('/dashboard')
def dashboard(
    request: Request,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    vehicle: str = Query(default='ALL', max_length=60),
    machine_id: str = Query(default='ALL', max_length=50),  # backward compatible with r2
    state: str = Query(default='ALL', max_length=20),
    shift: str = Query(default='ALL', max_length=10),
    mapping: str = Query(default='ALL', max_length=20),
    location: str = Query(default='ALL', max_length=80),
    db=Depends(get_db),
):
    user = get_user(db, request)
    require(user, module='DASHBOARD')
    today = datetime.now(IST).date()
    from_date = from_date or (today - timedelta(days=6))
    to_date = to_date or today
    shift = shift.upper()
    if shift not in VALID_SHIFTS:
        raise HTTPException(422, 'Shift must be ALL, A, B or C.')
    if from_date > to_date:
        raise HTTPException(422, 'From date cannot be after To date.')
    if (to_date - from_date).days > 92:
        raise HTTPException(422, 'Select a maximum range of 93 days.')

    now = datetime.now(timezone.utc)
    operational_vins, current_shift, shift_started_at = _shift_operational_vins(db, now)
    zones = _location_zones(db)
    latest = _latest_payloads(db)
    recent_statuses = _recent_status_pairs(db)
    mappings = {r.vin: r.machine_id for r in db.scalars(select(VolvoMapping))}
    all_vehicles = list(db.scalars(select(VolvoVehicle).order_by(VolvoVehicle.vin)))
    labels = {
        v.vin: (v.payload.get('customerVehicleName') or v.payload.get('vehicleName') or v.vin[-6:])
        for v in all_vehicles
    }
    filter_vehicles = []
    for v in all_vehicles:
        mapped = mappings.get(v.vin)
        name = labels[v.vin]
        filter_vehicles.append({
            'vin': v.vin,
            'name': name,
            'machine_id': mapped,
            'label': name + (f' · TIOM {mapped}' if mapped else ' · TIOM unmapped'),
        })

    selected_vehicle = vehicle
    if selected_vehicle == 'ALL' and machine_id != 'ALL':
        selected_vehicle = machine_id

    vehicle_rows = []
    for v in all_vehicles:
        row = _assign_location(_fleet_row(v, mappings, latest, recent_statuses, now, operational_vins), zones)
        if selected_vehicle != 'ALL' and selected_vehicle not in {row['vin'], row['machine_id'], row['name']}:
            continue
        if location == 'UNASSIGNED' and row['location_id'] is not None:
            continue
        if location not in {'ALL','UNASSIGNED'} and row['location_id'] != location:
            continue
        if state != 'ALL' and row['state'] != state:
            continue
        if mapping == 'MAPPED' and not row['machine_id']:
            continue
        if mapping == 'UNMAPPED' and row['machine_id']:
            continue
        vehicle_rows.append(row)

    allowed_vins = {r['vin'] for r in vehicle_rows}
    start_utc, end_utc = _period_bounds(from_date, to_date)
    status_reports = db.scalars(
        select(VolvoReport)
        .where(
            VolvoReport.kind == 'vehiclestatuses',
            VolvoReport.vin.in_(allowed_vins),
            VolvoReport.created_at >= start_utc,
            VolvoReport.created_at < end_utc,
        )
        .order_by(VolvoReport.vin, VolvoReport.created_at)
    ).all() if allowed_vins else []
    if allowed_vins:
        # Add the last reading before the requested period for each VIN. This is
        # used only as the baseline for the first in-range interval.
        for vin in allowed_vins:
            previous = db.scalar(
                select(VolvoReport)
                .where(
                    VolvoReport.kind == 'vehiclestatuses',
                    VolvoReport.vin == vin,
                    VolvoReport.created_at < start_utc,
                )
                .order_by(VolvoReport.created_at.desc())
                .limit(1)
            )
            if previous is not None:
                status_reports.append(previous)
    period_vehicles, daily, totals = _period_metrics(
        status_reports, mappings, labels, allowed_vins, from_date, to_date, shift
    )

    counts = defaultdict(int)
    for row in vehicle_rows:
        counts[row['state']] += 1
    sync = db.scalar(select(VolvoSync).order_by(VolvoSync.completed_at.desc()).limit(1))
    equipment = [
        {'id': e.machine_id, 'label': e.door_no or e.vehicle_no or e.machine_id}
        for e in db.scalars(select(Equipment).where(Equipment.active.is_(True)).order_by(Equipment.machine_id))
    ] if user.admin else []
    return {
        'from_date': from_date,
        'to_date': to_date,
        'shift': shift,
        'server_time': now,
        'last_sync': sync.completed_at if sync else None,
        'fleet': vehicle_rows,
        'state_counts': dict(counts),
        'operational_count': sum(1 for row in vehicle_rows if row['operational']),
        'current_shift': current_shift,
        'shift_started_at': shift_started_at,
        'period_vehicles': period_vehicles,
        'daily': daily,
        'totals': totals,
        'can_map': user.admin,
        'equipment': equipment,
        'filters': {
            'vehicles': filter_vehicles,
            'states': ['RUNNING', 'IDLE', 'STOPPED', 'OFFLINE'],
            'shifts': ['ALL', 'A', 'B', 'C'],
            'locations': [{'id':z['location_id'],'name':z['location_name'],'type':z['location_type']} for z in zones],
        },
        'location_zones': zones,
        'selected_location': location,
    }


def _haversine_km(a, b):
    lat1, lon1 = math.radians(a['latitude']), math.radians(a['longitude'])
    lat2, lon2 = math.radians(b['latitude']), math.radians(b['longitude'])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))


@router.get('/route/{vin}')
def vehicle_route(
    vin: str,
    request: Request,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    shift: str = Query(default='ALL', max_length=10),
    limit: int = Query(default=1500, ge=50, le=3000),
    db=Depends(get_db),
):
    user = get_user(db, request)
    require(user, module='DASHBOARD')
    vehicle = db.get(VolvoVehicle, vin)
    if vehicle is None:
        raise HTTPException(404, 'Unknown Volvo vehicle.')
    today = datetime.now(IST).date()
    from_date = from_date or today
    to_date = to_date or today
    shift = shift.upper()
    if shift not in VALID_SHIFTS:
        raise HTTPException(422, 'Shift must be ALL, A, B or C.')
    if from_date > to_date or (to_date - from_date).days > 31:
        raise HTTPException(422, 'Route history supports a maximum range of 32 days.')
    start_utc, end_utc = _period_bounds(from_date, to_date)
    reports = db.scalars(
        select(VolvoReport)
        .where(
            VolvoReport.vin == vin,
            VolvoReport.kind.in_(['vehiclepositions', 'vehiclestatuses']),
            VolvoReport.created_at >= start_utc,
            VolvoReport.created_at < end_utc,
        )
        .order_by(VolvoReport.created_at, VolvoReport.fetched_at)
    ).all()
    points = []
    seen = set()
    latest_status = {
        'fuel_total_l': None,
        'engine_hours': None,
        'engine_speed_rpm': None,
        'driver_id': None,
        'driver_working_state': None,
    }
    for report in reports:
        if report.kind == 'vehiclepositions':
            pv = _position_values(report.payload)
            gps = pv['gps']
            when = timestamp((gps or {}).get('positionDateTime')) or timestamp(pv['reported_at']) or report.created_at
            speed = pv['gps_speed_kmh'] if pv['gps_speed_kmh'] is not None else pv['wheel_speed_kmh']
            heading = pv['heading']
            altitude = pv['altitude_m']
        else:
            sv = _status_values(report.payload)
            if sv['fuel_ml'] is not None:
                latest_status['fuel_total_l'] = sv['fuel_ml'] / 1000.0
            if sv['engine_hours'] is not None:
                latest_status['engine_hours'] = sv['engine_hours']
            if sv['engine_speed_rpm'] is not None:
                latest_status['engine_speed_rpm'] = sv['engine_speed_rpm']
            if sv['driver_id']:
                latest_status['driver_id'] = sv['driver_id']
            if sv['driver_working_state']:
                latest_status['driver_working_state'] = sv['driver_working_state']
            gps = sv['gps']
            when = timestamp((gps or {}).get('positionDateTime')) or timestamp(sv['reported_at']) or report.created_at
            speed = _num((gps or {}).get('speed')) if isinstance(gps, dict) else sv['wheel_speed_kmh']
            heading = _num((gps or {}).get('heading')) if isinstance(gps, dict) else None
            altitude = _num((gps or {}).get('altitude')) if isinstance(gps, dict) else None
        if not isinstance(gps, dict) or not _in_operating_range(when, from_date, to_date, shift):
            continue
        lat = _num(gps.get('latitude'))
        lon = _num(gps.get('longitude'))
        if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
            continue
        if when and when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        key = (when.isoformat() if when else '', round(lat, 6), round(lon, 6))
        if key in seen:
            continue
        seen.add(key)
        op_date, op_shift = _operating_date_shift(when)
        points.append({
            'latitude': lat,
            'longitude': lon,
            'reported_at': when,
            'speed_kmh': speed,
            'heading': heading,
            'altitude_m': altitude,
            'operating_date': op_date,
            'shift': op_shift,
            'source': report.kind,
            'fuel_total_l': latest_status['fuel_total_l'],
            'engine_hours': latest_status['engine_hours'],
            'engine_speed_rpm': latest_status['engine_speed_rpm'],
            'driver_id': latest_status['driver_id'],
            'driver_working_state': latest_status['driver_working_state'],
        })
    points.sort(key=lambda x: x['reported_at'] or datetime.min.replace(tzinfo=timezone.utc))

    cumulative_km = 0.0
    fuel_baseline_l = next((p['fuel_total_l'] for p in points if p.get('fuel_total_l') is not None), None)
    first_time = next((p['reported_at'] for p in points if p.get('reported_at') is not None), None)
    stop_started_at = None
    for i, point in enumerate(points):
        segment_km = 0.0
        segment_seconds = 0.0
        if i > 0:
            previous = points[i - 1]
            segment_km = _haversine_km(previous, point)
            if previous.get('reported_at') and point.get('reported_at'):
                segment_seconds = max(0.0, (point['reported_at'] - previous['reported_at']).total_seconds())
            cumulative_km += segment_km
        point['segment_km'] = round(segment_km, 3)
        point['cumulative_km'] = round(cumulative_km, 3)
        point['segment_seconds'] = round(segment_seconds, 1)
        point['elapsed_seconds'] = round(max(0.0, (point['reported_at'] - first_time).total_seconds()), 1) if first_time and point.get('reported_at') else None
        point['fuel_used_l'] = round(max(0.0, point['fuel_total_l'] - fuel_baseline_l), 2) if fuel_baseline_l is not None and point.get('fuel_total_l') is not None else None

        stationary = point.get('speed_kmh') is not None and float(point['speed_kmh']) <= 1.0
        if stationary and segment_km <= 0.05:
            if stop_started_at is None:
                stop_started_at = point.get('reported_at')
            point['stop_seconds'] = round(max(0.0, (point['reported_at'] - stop_started_at).total_seconds()), 1) if stop_started_at and point.get('reported_at') else 0.0
        else:
            stop_started_at = None
            point['stop_seconds'] = 0.0

    # Assign configured TIOM GPS zones to route points when available.
    zones = _location_zones(db)
    for point in points:
        wrapper = {'gps': {'latitude': point['latitude'], 'longitude': point['longitude']}}
        _assign_location(wrapper, zones)
        point['location_id'] = wrapper.get('location_id')
        point['location_name'] = wrapper.get('location_name')

    # Split the session into movement trips. Until source/destination geofences are
    # fully configured, a trip boundary is a >=3 minute stationary period or a
    # >=15 minute telemetry gap. This is intentionally conservative.
    trips = []
    trip_start = None
    stop_start = None

    def close_trip(start_idx, end_idx):
        if start_idx is None or end_idx is None or end_idx <= start_idx:
            return
        segment = points[start_idx:end_idx + 1]
        start_at = segment[0].get('reported_at')
        end_at = segment[-1].get('reported_at')
        distance_km = 0.0
        stop_total = 0.0
        moving_seconds = 0.0
        for j in range(1, len(segment)):
            distance_km += _haversine_km(segment[j - 1], segment[j])
            sec = float(segment[j].get('segment_seconds') or 0.0)
            stationary = (
                (segment[j].get('speed_kmh') is not None and float(segment[j]['speed_kmh']) <= 1.0)
                and float(segment[j].get('segment_km') or 0.0) <= 0.05
            )
            if stationary:
                stop_total += sec
            else:
                moving_seconds += sec
        duration_seconds = max(0.0, (end_at - start_at).total_seconds()) if start_at and end_at else 0.0
        # Ignore tiny GPS jitter sessions.
        if distance_km < 0.15 and duration_seconds < 120:
            return
        first_fuel = next((p.get('fuel_total_l') for p in segment if p.get('fuel_total_l') is not None), None)
        last_fuel = next((p.get('fuel_total_l') for p in reversed(segment) if p.get('fuel_total_l') is not None), None)
        fuel_l = max(0.0, last_fuel - first_fuel) if first_fuel is not None and last_fuel is not None else None
        configured_locations = [p for p in segment if p.get('location_id')]
        source_name = configured_locations[0].get('location_name') if configured_locations else None
        destination_name = configured_locations[-1].get('location_name') if configured_locations else None
        trip_id = f"T{len(trips) + 1:03d}"
        trip_cum = 0.0
        previous = None
        for p in segment:
            if previous is not None:
                trip_cum += _haversine_km(previous, p)
            p['trip_id'] = trip_id
            p['trip_cumulative_km'] = round(trip_cum, 3)
            previous = p
        trips.append({
            'trip_id': trip_id,
            'start_at': start_at,
            'end_at': end_at,
            'duration_seconds': round(duration_seconds, 1),
            'moving_seconds': round(moving_seconds, 1),
            'stop_seconds': round(stop_total, 1),
            'distance_km': round(distance_km, 2),
            'fuel_l': round(fuel_l, 2) if fuel_l is not None else None,
            'avg_speed_kmh': round(distance_km / (duration_seconds / 3600.0), 1) if duration_seconds > 0 else None,
            'point_count': len(segment),
            'source_name': source_name,
            'destination_name': destination_name,
            'start_index': start_idx,
            'end_index': end_idx,
        })

    for i, point in enumerate(points):
        moving = (
            (point.get('speed_kmh') is not None and float(point['speed_kmh']) > 1.0)
            or float(point.get('segment_km') or 0.0) > 0.05
        )
        gap_seconds = float(point.get('segment_seconds') or 0.0)
        if trip_start is not None and gap_seconds >= 900:
            close_trip(trip_start, i - 1)
            trip_start = i if moving else None
            stop_start = None
            continue
        if trip_start is None:
            if moving:
                trip_start = max(0, i - 1)
            continue
        if moving:
            stop_start = None
            continue
        if stop_start is None:
            stop_start = i
        stop_duration = float(point.get('stop_seconds') or 0.0)
        if stop_duration >= 180:
            close_trip(trip_start, stop_start)
            trip_start = None
            stop_start = None

    if trip_start is not None:
        close_trip(trip_start, len(points) - 1)

    raw_count = len(points)
    route_km = cumulative_km
    current_trip_id = trips[-1]['trip_id'] if trips else None
    if trips and points:
        last_reported = points[-1].get('reported_at')
        now_utc = datetime.now(timezone.utc)
        recent = bool(last_reported and (now_utc - last_reported).total_seconds() <= 600)
        trips[-1]['is_current'] = recent
    for trip in trips[:-1]:
        trip['is_current'] = False

    # Display sampling happens after trip assignment so trip IDs survive.
    if len(points) > limit:
        selected_indexes = {0, len(points) - 1}
        for trip in trips:
            selected_indexes.add(trip['start_index'])
            selected_indexes.add(trip['end_index'])
        remaining = max(0, limit - len(selected_indexes))
        if remaining:
            candidates = [i for i in range(len(points)) if i not in selected_indexes]
            if len(candidates) > remaining:
                step = len(candidates) / remaining
                selected_indexes.update(candidates[min(len(candidates) - 1, int(i * step))] for i in range(remaining))
            else:
                selected_indexes.update(candidates)
        points = [points[i] for i in sorted(selected_indexes)[:limit]]

    mapping = db.get(VolvoMapping, vin)
    return {
        'vin': vin,
        'name': vehicle.payload.get('customerVehicleName') or vehicle.payload.get('vehicleName') or vin[-6:],
        'machine_id': mapping.machine_id if mapping else None,
        'from_date': from_date,
        'to_date': to_date,
        'shift': shift,
        'point_count': raw_count,
        'returned_points': len(points),
        'route_km': round(route_km, 2),
        'trip_count': len(trips),
        'trips': trips,
        'current_trip_id': current_trip_id,
        'points': points,
        'precision_note': 'Trips are segmented from Volvo GNSS movement using stops >=3 minutes or telemetry gaps >=15 minutes. Configure TIOM GPS location zones to add reliable Source/Destination labels. The trail is not road-snapped; route precision depends on GNSS/reporting frequency.',
    }


@lru_cache(maxsize=256)
def _osm_tile(z: int, x: int, y: int) -> bytes:
    req = urllib.request.Request(
        f'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        headers={'User-Agent': 'NMTPL-TIOM-Internal-Volvo-Dashboard/1.0'},
    )
    with urllib.request.urlopen(req, timeout=8) as response:
        raw = response.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValueError('Map tile too large')
    return raw


@lru_cache(maxsize=256)
def _satellite_tile(z: int, x: int, y: int) -> bytes:
    req = urllib.request.Request(
        f'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        headers={'User-Agent': 'NMTPL-TIOM-Internal-Volvo-Dashboard/1.0'},
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Satellite tile too large')
    return raw


@router.get('/map-tile/{z}/{x}/{y}.png')
def map_tile(
    z: int, x: int, y: int, request: Request,
    layer: str = Query(default='street', max_length=20),
    db=Depends(get_db),
):
    user = get_user(db, request)
    require(user, module='DASHBOARD')
    if z < 0 or z > 18:
        raise HTTPException(404, 'Map tile not found.')
    max_tile = 2 ** z
    if x < 0 or y < 0 or x >= max_tile or y >= max_tile:
        raise HTTPException(404, 'Map tile not found.')
    layer = str(layer or 'street').strip().lower()
    try:
        if layer == 'satellite':
            raw = _satellite_tile(z, x, y)
            media_type = 'image/jpeg'
        else:
            raw = _osm_tile(z, x, y)
            media_type = 'image/png'
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        raise HTTPException(503, 'Map tiles temporarily unavailable.') from None
    cache_seconds = 300 if layer == 'satellite' else 86400
    return Response(raw, media_type=media_type, headers={'Cache-Control': f'private, max-age={cache_seconds}'})


class LocationZoneInput(BaseModel):
    location_id: str = Field(min_length=1, max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: float = Field(default=300, ge=50, le=5000)


@router.get('/location-zones')
def location_zones(request: Request, db=Depends(get_db)):
    user=get_user(db,request)
    require(user,module='DASHBOARD')
    _ensure_location_zone_table(db)
    configured=_location_zones(db)
    available=[
        {'id':x.location_id,'name':x.location_name,'type':x.location_type}
        for x in db.scalars(select(Location).where(Location.active.is_(True)).order_by(Location.location_name,Location.location_id))
    ]
    return {'zones':configured,'available':available,'can_edit':bool(user.admin)}


@router.post('/location-zones')
def save_location_zone(body: LocationZoneInput, request: Request, db=Depends(get_db)):
    user=get_user(db,request)
    require(user,admin=True)
    csrf(request)
    _ensure_location_zone_table(db)
    loc=db.get(Location,body.location_id)
    if not loc or not loc.active:
        raise HTTPException(422,'Choose an active TIOM location.')
    zone=db.get(VolvoLocationZone,body.location_id)
    now=datetime.now(timezone.utc)
    if zone:
        zone.latitude=body.latitude
        zone.longitude=body.longitude
        zone.radius_m=body.radius_m
        zone.changed_by=user.login_id
        zone.changed_at=now
    else:
        db.add(VolvoLocationZone(
            location_id=body.location_id,latitude=body.latitude,longitude=body.longitude,
            radius_m=body.radius_m,changed_by=user.login_id,changed_at=now,
        ))
    db.commit()
    return {'ok':True}


@router.delete('/location-zones/{location_id}')
def delete_location_zone(location_id: str, request: Request, db=Depends(get_db)):
    user=get_user(db,request)
    require(user,admin=True)
    csrf(request)
    _ensure_location_zone_table(db)
    zone=db.get(VolvoLocationZone,location_id)
    if zone:
        db.delete(zone)
        db.commit()
    return {'ok':True}


class MappingInput(BaseModel):
    vin: str = Field(min_length=17, max_length=17)
    machine_id: str | None = Field(default=None, max_length=50)


@router.post('/mapping')
def mapping(body: MappingInput, request: Request, db=Depends(get_db)):
    user = get_user(db, request)
    require(user, admin=True)
    csrf(request)
    vehicle = db.scalar(select(VolvoVehicle).where(VolvoVehicle.vin == body.vin).with_for_update())
    if vehicle is None:
        raise HTTPException(404, 'Unknown Volvo vehicle.')
    if body.machine_id:
        equipment = db.get(Equipment, body.machine_id)
        if not equipment or not equipment.active:
            raise HTTPException(422, 'Choose an active equipment record.')
    current = db.get(VolvoMapping, body.vin)
    old = current.machine_id if current else None
    new = body.machine_id or None
    if old == new:
        return {'ok': True}
    now = datetime.now(timezone.utc)
    if not new:
        if current:
            db.delete(current)
    elif current:
        current.machine_id, current.changed_by, current.changed_at = new, user.login_id, now
    else:
        db.add(VolvoMapping(vin=body.vin, machine_id=new, changed_by=user.login_id, changed_at=now))
    db.add(VolvoAudit(
        id=str(uuid.uuid4()), vin=body.vin, old_machine_id=old,
        new_machine_id=new, actor=user.login_id, changed_at=now,
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'That equipment is already linked to another Volvo vehicle.') from None
    return {'ok': True}
