"""Time basis for fleet/route throughput (not vehicle running-hour efficiency)."""
from datetime import datetime, timedelta


def reporting_hours(first_day, last_day, definitions, now):
    """Union of scheduled shift windows, capped at now; idle time is included.

    Shift dates are operating dates, so an overnight shift ends the next day.
    Overlapping master windows must not double-count hours for ALL shifts.
    """
    intervals = []
    day = first_day
    definitions = list(definitions)
    if not definitions:
        return None
    while day <= last_day:
        for definition in definitions:
            start = datetime.combine(day, definition.start_time, now.tzinfo)
            end = datetime.combine(day, definition.end_time, now.tzinfo)
            if end <= start:
                end += timedelta(days=1)
            end = min(end, now)
            if end > start:
                intervals.append((start, end))
        day += timedelta(days=1)
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return sum((end - start).total_seconds() for start, end in merged) / 3600
