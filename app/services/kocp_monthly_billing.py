"""KOCP month-end MCL certified average reconciliation.

Daily operational averages remain saved on trips, unchanged.
Only *approved* MCL_MONTHLY factors covering the full billing period can
calculate the final billable amount. All trips must have a matching rule.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Equipment
from app.site_models import SiteTrip, SiteWeightFactor
from app.services.kocp_factor_rules import choose_point_factor

QTY = Decimal("0.001")


def month_end_factor_reconciliation(db: Session, *, site_id: str, material_id: str,
                                     from_date, to_date, is_ob: bool) -> dict | None:
    if site_id != "KOCP":
        return None
    factor_type = "OB_CUM_PER_TRIP" if is_ob else "COAL_AVG_MT_PER_TRIP"
    factors = list(db.scalars(select(SiteWeightFactor).where(
        SiteWeightFactor.site_id == site_id,
        SiteWeightFactor.factor_type == factor_type,
        SiteWeightFactor.source_org == "MCL_MONTHLY",
        SiteWeightFactor.status == "APPROVED",
        SiteWeightFactor.material_id == material_id,
        SiteWeightFactor.effective_from <= from_date,
        SiteWeightFactor.effective_to >= to_date,
    )).all())
    if not factors:
        return None
    trips = list(db.scalars(select(SiteTrip).where(
        SiteTrip.site_id == site_id, SiteTrip.material_id == material_id,
        SiteTrip.status == "POSTED",
        SiteTrip.operating_date >= from_date,
        SiteTrip.operating_date <= to_date,
    ).order_by(SiteTrip.operating_date, SiteTrip.trip_id)).all())
    if not trips:
        raise HTTPException(409, "No posted trips found for this MCL billing period.")
    machine_ids = sorted({t.vehicle_id for t in trips if t.vehicle_id})
    vehicles = {
        e.machine_id: e for e in db.scalars(select(Equipment).where(
            Equipment.machine_id.in_(machine_ids)
        ))
    } if machine_ids else {}
    total = Decimal("0")
    details = {}
    trip_digest = sha256()
    for trip in trips:
        # Bind the approval to the source trip identities and revisions,
        # not only the aggregate count (which could stay the same).
        trip_digest.update((
            f"{trip.trip_id}|{trip.version}|{trip.operating_date}|"
            f"{trip.vehicle_id}|{trip.destination_location_id}|"
            f"{trip.route_id}|{trip.material_id}|{trip.shift}\n"
        ).encode("utf-8"))
        machine = vehicles.get(trip.vehicle_id)
        try:
            rate = choose_point_factor(
                factors, operating_day=trip.operating_date, shift=trip.shift,
                destination_id=trip.destination_location_id,
                route_id=trip.route_id, material_id=material_id,
                vehicle_type=machine.type if machine else None,
                vehicle_group=machine.group if machine else None,
                vehicle_model=machine.make_model if machine else None,
                allowed_sources=("MCL_MONTHLY",),
            )
        except HTTPException as ex:
            raise HTTPException(
                409, f"Final MCL monthly rate is missing or conflicted for "
                     f"trip {trip.trip_id} ({trip.operating_date}): {ex.detail}"
            ) from ex
        total += Decimal(str(rate.factor_value))
        key = rate.factor_id
        if key not in details:
            details[key] = {
                "factorId": key, "materialId": material_id,
                "destinationLocationId": rate.destination_location_id,
                "routeId": rate.route_id, "vehicleClass": rate.vehicle_class,
                "rate": str(rate.factor_value), "reference": rate.reference_no,
                "trips": 0,
            }
        details[key]["trips"] += 1
    return {
        "basis": "MCL_MONTHLY_AVERAGE",
        "total": str(total.quantize(QTY, rounding=ROUND_HALF_UP)),
        "trips": len(trips),
        "tripChecksum": trip_digest.hexdigest(),
        "unit": "CuM" if is_ob else "MT",
        "rules": list(details.values()),
        "periodStart": from_date.isoformat(), "periodEnd": to_date.isoformat(),
    }
