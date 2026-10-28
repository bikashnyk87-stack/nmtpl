"""Run the existing TIOM app silently on LOCALHOST:8765 when a user signs in.

No public/LAN binding: LAN access is a separate, explicitly trusted-network
installer. Never modifies the WB or Despatch synchronization mechanisms.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app" / "main.py").is_file():
    raise SystemExit("Existing PC TIOM app not found at " + str(ROOT))

os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = ROOT / "logs" / "local_server" / "uvicorn_8765.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    with LOG.open("a", encoding="utf-8", buffering=1) as output:
        out, err = sys.stdout, sys.stderr
        try:
            sys.stdout, sys.stderr = output, output
            print(f"LOCAL_TIOM_8765_START={datetime.now(timezone.utc).isoformat()}")
            import uvicorn
            uvicorn.run(
                "app.main:app",
                host="127.0.0.1",
                port=8765,
                access_log=False,
                proxy_headers=False,
                log_level="info",
            )
        except Exception:
            import traceback
            traceback.print_exc(file=output)
            raise
        finally:
            sys.stdout, sys.stderr = out, err


if __name__ == "__main__":
    main()
