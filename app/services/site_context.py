from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.site_models import Site, SiteShift


@dataclass(frozen=True)
class SiteOperatingContext:
    site_id: str
    operating_date: date
    shift: str
    local_at: datetime


def _contains(clock: time, start: time, end: time) -> bool:
    if start < end:
        return start <= clock < end
    return clock >= start or clock < end


def resolve_site_context(db, site_id: str, at: datetime | None = None) -> SiteOperatingContext:
    site = db.get(Site, site_id.upper())
    if not site or not site.active:
        raise ValueError(f"Unknown or inactive site: {site_id}")
    zone = ZoneInfo(site.timezone or "Asia/Kolkata")
    if at is None:
        local = datetime.now(zone)
    elif at.tzinfo is None:
        local = at.replace(tzinfo=zone)
    else:
        local = at.astimezone(zone)

    shifts = list(db.scalars(
        select(SiteShift)
        .where(SiteShift.site_id == site.site_id, SiteShift.active.is_(True))
        .order_by(SiteShift.sequence_no, SiteShift.shift)
    ))
    for definition in shifts:
        if not _contains(local.timetz().replace(tzinfo=None), definition.start_time, definition.end_time):
            continue
        operating_day = local.date()
        if definition.start_time > definition.end_time and local.timetz().replace(tzinfo=None) < definition.end_time:
            operating_day -= timedelta(days=1)
        return SiteOperatingContext(site.site_id, operating_day, definition.shift, local)
    raise ValueError(f"No active shift covers {local.isoformat()} for {site.site_id}")


def seed_default_sites_and_shifts(db) -> None:
    defaults = {
        "TIOM": ("Thakurani Iron Ore Mine", "TIOM"),
        "SOCP": ("SOCP", "SOCP"),
        "KOCP": ("KOCP", "KOCP"),
    }
    for site_id, (name, short) in defaults.items():
        if not db.get(Site, site_id):
            db.add(Site(site_id=site_id, site_name=name, short_name=short, timezone="Asia/Kolkata", active=True))
    db.flush()

    shift_defaults = {
        "SOCP": {
            "A": (time(6, 0), time(14, 0), 1),
            "B": (time(14, 0), time(22, 0), 2),
            "C": (time(22, 0), time(6, 0), 3),
        },
        "KOCP": {
            "A": (time(5, 0), time(13, 0), 1),
            "B": (time(13, 0), time(21, 0), 2),
            "C": (time(21, 0), time(5, 0), 3),
        },
    }
    for site_id, shifts in shift_defaults.items():
        for shift, (start, end, seq) in shifts.items():
            row = db.get(SiteShift, {"site_id": site_id, "shift": shift})
            if not row:
                db.add(SiteShift(
                    site_id=site_id,
                    shift=shift,
                    shift_name=f"Shift {shift}",
                    start_time=start,
                    end_time=end,
                    scheduled_hours=8,
                    sequence_no=seq,
                    active=True,
                ))

    # TIOM follows the existing ShiftMaster during the transition so the
    # production pilot is not silently reconfigured.
    try:
        from app.models import ShiftMaster
        legacy = list(db.scalars(select(ShiftMaster).where(ShiftMaster.active.is_(True))))
        for idx, old in enumerate(legacy, start=1):
            row = db.get(SiteShift, {"site_id": "TIOM", "shift": old.shift})
            if not row:
                db.add(SiteShift(
                    site_id="TIOM",
                    shift=old.shift,
                    shift_name=f"Shift {old.shift}",
                    start_time=old.start_time,
                    end_time=old.end_time,
                    scheduled_hours=old.scheduled_hours,
                    sequence_no=idx,
                    active=True,
                ))
    except Exception:
        # The migration script may be run before legacy masters are initialized.
        pass
