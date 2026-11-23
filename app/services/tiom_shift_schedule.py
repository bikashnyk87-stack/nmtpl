"""TIOM operating-shift schedule with its approved 1-Oct-2026 changeover.

An operating date, not the calendar date of an overnight weighment, controls
which schedule applies. This module does not change SOCP/KOCP schedules or
rewrite previously confirmed WB records.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from app.services.time_context import TZ

EFFECTIVE_DATE = date(2026, 10, 1)
OLD_TIMES = {
    "A": (time(5, 0), time(13, 0)),
    "B": (time(13, 0), time(21, 0)),
    "C": (time(21, 0), time(5, 0)),
}
NEW_TIMES = {
    "A": (time(6, 0), time(14, 0)),
    "B": (time(14, 0), time(22, 0)),
    "C": (time(22, 0), time(6, 0)),
}


def times_for_day(operating_day: date, shift: str) -> tuple[time, time]:
    schedule = NEW_TIMES if operating_day >= EFFECTIVE_DATE else OLD_TIMES
    return schedule[str(shift).upper()]


def definition_for_day(operating_day: date, definition):
    """Immutable, date-scoped shape for existing helpers using start/end time."""
    if definition is None:
        return None
    start, end = times_for_day(operating_day, definition.shift)
    return SimpleNamespace(
        shift=definition.shift, start_time=start, end_time=end,
        active=definition.active,
        scheduled_hours=definition.scheduled_hours,
    )


def context_at(at: datetime) -> tuple[date, str] | None:
    """Return TIOM operating date and shift for the physical instant.

    Candidate operating days include yesterday so post-midnight C belongs to
    the day it started. The 1-Oct 05:00-06:00 changeover gap is deliberately
    not guessed or silently assigned to an unapproved shift.
    """
    local = at.replace(tzinfo=TZ) if at.tzinfo is None else at.astimezone(TZ)
    for operating_day in (local.date(), local.date() - timedelta(days=1)):
        for shift in ("A", "B", "C"):
            start, end = times_for_day(operating_day, shift)
            begin = datetime.combine(operating_day, start, TZ)
            finish = datetime.combine(operating_day, end, TZ)
            if finish <= begin:
                finish += timedelta(days=1)
            if begin <= local < finish:
                return operating_day, shift
    return None
