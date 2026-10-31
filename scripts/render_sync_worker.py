from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pull_render_sync import CONFIG_PATH, logger, sync_once, _write_status

IST = timezone(timedelta(hours=5, minutes=30))
FIRST_SYNC_HOUR = 6
LAST_SYNC_HOUR = 22


def next_sync_slot(now: datetime) -> datetime:
    """06:00–22:00 IST on exact hourly boundaries, including 22:00."""
    here = now.astimezone(IST)
    for offset in range(2):
        day = here.date() + timedelta(days=offset)
        for hour in range(FIRST_SYNC_HOUR, LAST_SYNC_HOUR + 1):
            due = datetime.combine(day, datetime.min.time(), IST).replace(hour=hour)
            if due >= here:
                return due
    raise RuntimeError("Failed to find the next PC sync slot")


def main():
    logger.info("PC to Neon sync: hourly 06:00–22:00 IST; idle outside this window.")
    # Keep the existing cursor, baseline state, conflict handling and PC->cloud
    # uploads unchanged. Only the timing of the complete sync cycle changes.
    due = next_sync_slot(datetime.now(timezone.utc))
    while True:
        try:
            seconds = (due - datetime.now(timezone.utc).astimezone(IST)).total_seconds()
            if seconds > 0:
                time.sleep(min(60, seconds))
                continue
            logger.info("PC sync scheduled slot: %s", due.isoformat())
            try:
                sync_once()
            except Exception as exc:
                logger.exception("Scheduled PC sync failed")
                _write_status(state="ERROR", error=f"{type(exc).__name__}: {exc}",
                              scheduled_for=due.isoformat())
            finally:
                # Catch up at the next permitted hour, never run in a tight
                # loop on failure or wake Neon overnight.
                due = next_sync_slot(datetime.now(timezone.utc) + timedelta(seconds=2))
        except KeyboardInterrupt:
            logger.info("PC sync worker stopped by keyboard interrupt")
            _write_status(state="STOPPED")
            return


if __name__ == "__main__":
    main()
