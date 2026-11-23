from __future__ import annotations
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from . import __init__  # noqa: F401
from app.config import settings

TZ = ZoneInfo(settings.timezone)

# Current TIOM master timings; date-effective history is resolved by
# app.services.tiom_shift_schedule.context_at, not this compatibility mapping.
SHIFT_DEF = {
    "A": (time(6,0), time(14,0)),
    "B": (time(14,0), time(22,0)),
    "C": (time(22,0), time(6,0)),
}

def now_local() -> datetime:
    return datetime.now(TZ)

def operating_context(at: datetime | None = None) -> tuple[datetime.date, str, datetime]:
    from app.services.tiom_shift_schedule import context_at
    at = at.astimezone(TZ) if at and at.tzinfo else (at.replace(tzinfo=TZ) if at else now_local())
    context = context_at(at)
    if context is None:
        raise ValueError(f"No approved TIOM shift covers {at.isoformat()}")
    day, shift = context
    return day, shift, at

def week_monday(day):
    return day - timedelta(days=day.weekday())
