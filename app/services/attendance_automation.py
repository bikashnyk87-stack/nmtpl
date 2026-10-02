from __future__ import annotations

import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    AuditLog, LoadTrip, PersonAttendance, ShiftCrew, ShiftDeployment, ShiftMaster
)
from app.services.time_context import TZ, now_local

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "operations_automation.json"
LOG_DIR = ROOT / "logs"
LOG_PATH = LOG_DIR / "attendance_automation.log"

DEFAULT_CONFIG = {
    "attendance_auto_close_enabled": True,
    "attendance_auto_close_grace_minutes": 30,
    "attendance_check_seconds": 300,
}

logger = logging.getLogger("attendance_automation")
logger.setLevel(logging.INFO)
if not logger.handlers:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)


def load_config():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        return dict(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        logger.exception("Invalid operations_automation.json; defaults used.")
        return dict(DEFAULT_CONFIG)
    out = dict(DEFAULT_CONFIG)
    out.update({k: data[k] for k in DEFAULT_CONFIG if k in data})
    return out


def shift_bounds(day, definition):
    start = datetime.combine(day, definition.start_time, TZ)
    end = datetime.combine(day, definition.end_time, TZ)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def _audit(db, action, entity, entity_id, detail):
    db.add(AuditLog(
        created_at=now_local(),
        actor="SYSTEM_AUTO_CLOSE",
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        detail=json.dumps(detail, default=str),
    ))


def auto_close_shift(db, day, shift, *, actor="SYSTEM_AUTO_CLOSE", now=None, force=False):
    cfg = load_config()
    definition = db.get(ShiftMaster, shift)
    if not definition or not definition.active:
        return {"closed": 0, "releasedCrew": 0, "releasedDeployments": 0, "openTrips": 0}

    _, scheduled_end = shift_bounds(day, definition)
    now = now or now_local()
    grace = max(0, int(cfg.get("attendance_auto_close_grace_minutes", 30)))
    if not force and now <= scheduled_end + timedelta(minutes=grace):
        return {"closed": 0, "releasedCrew": 0, "releasedDeployments": 0, "openTrips": 0}

    missing = list(db.scalars(select(PersonAttendance).where(
        PersonAttendance.operating_date == day,
        PersonAttendance.shift == shift,
        PersonAttendance.status == "PRESENT",
        PersonAttendance.in_at.is_not(None),
        PersonAttendance.out_at.is_(None),
    )))

    active_crew = list(db.scalars(select(ShiftCrew).where(
        ShiftCrew.operating_date == day,
        ShiftCrew.shift == shift,
        ShiftCrew.status == "ACTIVE",
    )))
    active_dep = list(db.scalars(select(ShiftDeployment).where(
        ShiftDeployment.operating_date == day,
        ShiftDeployment.shift == shift,
        ShiftDeployment.status == "ACTIVE",
    )))
    open_trips = list(db.scalars(select(LoadTrip).where(
        LoadTrip.operating_date == day,
        LoadTrip.shift == shift,
        LoadTrip.status.in_(["LOADING", "HAULING"]),
    )))

    missing_ids = {r.employee_id for r in missing}
    released_machines = set()
    released_crew = 0
    for crew in active_crew:
        if crew.employee_id not in missing_ids:
            continue
        crew.status = "CLOSED"
        crew.to_at = scheduled_end
        crew.reason = "AUTO_SHIFT_END: employee OUT was missing"
        crew.changed_by = actor
        crew.changed_at = now
        released_machines.add(crew.machine_id)
        released_crew += 1
        _audit(db, "AUTO_RELEASE_CREW", "shift_crew", crew.id, {
            "date": day, "shift": shift, "scheduledEnd": scheduled_end,
            "employeeId": crew.employee_id, "machineId": crew.machine_id,
        })

    released_dep = 0
    for dep in active_dep:
        if dep.machine_id not in released_machines:
            continue
        dep.status = "CLOSED"
        dep.to_at = scheduled_end
        dep.reason = "AUTO_SHIFT_END: crew attendance auto-closed"
        dep.changed_by = actor
        dep.changed_at = now
        released_dep += 1
        _audit(db, "AUTO_RELEASE_DEPLOYMENT", "shift_deployment", dep.id, {
            "date": day, "shift": shift, "scheduledEnd": scheduled_end,
            "machineId": dep.machine_id, "locationId": dep.location_id,
        })

    for row in missing:
        in_at = row.in_at
        if in_at.tzinfo is None:
            in_at = in_at.replace(tzinfo=TZ)
        else:
            in_at = in_at.astimezone(TZ)
        close_at = max(scheduled_end, in_at)
        row.out_at = close_at
        row.worked_hours = Decimal(str(round((close_at - in_at).total_seconds() / 3600, 2)))
        row.out_source = "AUTO_SHIFT_END"
        row.review_status = "REVIEW"
        note = "Auto-closed at scheduled shift end; HR review required."
        if note not in (row.remarks or ""):
            row.remarks = ((row.remarks + " | ") if row.remarks else "") + note
        _audit(db, "AUTO_OUT", "person_attendance", row.id, {
            "date": day,
            "shift": shift,
            "employeeId": row.employee_id,
            "outAt": close_at,
            "graceMinutes": grace,
            "openTripCountAtClose": len(open_trips),
        })

    if open_trips and missing:
        _audit(db, "SHIFT_CLOSE_OPEN_TRIP_WARNING", "load_trip", f"{day}/{shift}", {
            "tripIds": [x.trip_id for x in open_trips],
            "message": "Attendance was auto-closed but open production trips were not modified.",
        })

    return {
        "closed": len(missing),
        "releasedCrew": released_crew,
        "releasedDeployments": released_dep,
        "openTrips": len(open_trips),
    }


def run_overdue_cycle():
    cfg = load_config()
    if not cfg.get("attendance_auto_close_enabled", True):
        return {"enabled": False, "closed": 0}

    now = now_local()
    with SessionLocal() as db:
        candidates = list(db.execute(
            select(PersonAttendance.operating_date, PersonAttendance.shift)
            .where(
                PersonAttendance.status == "PRESENT",
                PersonAttendance.in_at.is_not(None),
                PersonAttendance.out_at.is_(None),
                PersonAttendance.operating_date >= (now.date() - timedelta(days=3)),
            )
            .distinct()
        ))
        total = {"enabled": True, "closed": 0, "releasedCrew": 0, "releasedDeployments": 0, "openTrips": 0}
        for day, shift in candidates:
            result = auto_close_shift(db, day, shift, now=now)
            for key in ("closed", "releasedCrew", "releasedDeployments", "openTrips"):
                total[key] += int(result.get(key, 0))
        if total["closed"] or total["releasedCrew"] or total["releasedDeployments"]:
            db.commit()
            logger.info("Attendance auto-close cycle: %s", total)
        else:
            db.rollback()
        return total


async def automation_loop():
    while True:
        cfg = load_config()
        delay = max(60, int(cfg.get("attendance_check_seconds", 300)))
        try:
            await asyncio.to_thread(run_overdue_cycle)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Attendance automation cycle failed")
        await asyncio.sleep(delay)
