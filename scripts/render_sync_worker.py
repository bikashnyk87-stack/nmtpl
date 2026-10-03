from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pull_render_sync import CONFIG_PATH, logger, sync_once, _write_status


def poll_seconds() -> int:
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        return max(60, int(cfg.get("poll_seconds", 180)))
    except Exception:
        return 180


def main():
    logger.info("NMTPL Render -> Base PC sync worker starting.")
    failures = 0
    while True:
        try:
            sync_once()
            failures = 0
            time.sleep(poll_seconds())
        except KeyboardInterrupt:
            logger.info("Sync worker stopped by keyboard interrupt.")
            _write_status(state="STOPPED")
            return
        except Exception as exc:
            failures += 1
            logger.exception("Sync cycle failed")
            _write_status(
                state="ERROR",
                error=f"{type(exc).__name__}: {exc}",
                consecutive_failures=failures,
            )
            time.sleep(min(900, max(60, failures * 60)))


if __name__ == "__main__":
    main()
