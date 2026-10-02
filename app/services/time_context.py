from __future__ import annotations
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from . import __init__  # noqa: F401
from app.config import settings

TZ = ZoneInfo(settings.timezone)

SHIFT_DEF = {
    "A": (time(5,0), time(13,0)),
    "B": (time(13,0), time(21,0)),
    "C": (time(21,0), time(5,0)),
}

def now_local() -> datetime:
    return datetime.now(TZ)

def operating_context(at: datetime | None = None) -> tuple[datetime.date, str, datetime]:
    at = at.astimezone(TZ) if at else now_local()
    t = at.timetz().replace(tzinfo=None)
    if time(5,0) <= t < time(13,0):
        shift = "A"
        day = at.date()
    elif time(13,0) <= t < time(21,0):
        shift = "B"
        day = at.date()
    else:
        shift = "C"
        day = at.date() if t >= time(21,0) else (at - timedelta(days=1)).date()
    return day, shift, at

def week_monday(day):
    return day - timedelta(days=day.weekday())
