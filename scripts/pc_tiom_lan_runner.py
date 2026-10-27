"""TIOM office-LAN runner (silent, logged, never touches WB sync cursors).

Installed to data/lan_server/ and run with the PC .venv pythonw.exe.
Serves the existing TIOM app on port 8765, on the owner's trusted office LAN.
Network exposure is constrained by an accompanying Private/LocalSubnet firewall
rule; do not use this runner on untrusted/public networks.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app" / "main.py").is_file():
    raise SystemExit("NMTPL TIOM PC application not found.")

os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "logs" / "lan_server"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "uvicorn_8765.log"


def main() -> None:
    # pythonw.exe has no console; a durable log is essential for diagnosis.
    with LOG_FILE.open("a", encoding="utf-8", buffering=1) as output:
        original_out, original_err = sys.stdout, sys.stderr
        try:
            sys.stdout = output
            sys.stderr = output
            print(f"TIOM_LAN_SERVER_START={datetime.now(timezone.utc).isoformat()}")
            import uvicorn
            uvicorn.run(
                "app.main:app",
                host="0.0.0.0",
                port=8765,
                log_level="info",
                access_log=False,
                proxy_headers=False,
            )
        except Exception:
            import traceback
            traceback.print_exc(file=output)
            raise
        finally:
            sys.stdout, sys.stderr = original_out, original_err


if __name__ == "__main__":
    main()
