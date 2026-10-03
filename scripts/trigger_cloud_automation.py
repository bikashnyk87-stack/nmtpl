from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ALLOWED = {"gmail", "volvo"}


def main() -> int:
    action = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if action not in ALLOWED:
        print("usage: python scripts/trigger_cloud_automation.py [gmail|volvo]")
        return 2

    base = os.getenv("TIOM_BASE_URL", "https://nmtpl-tiom-test.onrender.com").rstrip("/")
    key = os.getenv("NMTPL_AUTOMATION_KEY", "")
    if not key:
        print("NMTPL_AUTOMATION_KEY is not configured")
        return 3

    request = urllib.request.Request(
        f"{base}/api/automation/{action}",
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Automation-Key": key,
            "User-Agent": "NMTPL-Render-Automation/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read(1024 * 1024).decode("utf-8", "replace")
            print(body)
            return 0 if 200 <= response.status < 300 else 1
    except urllib.error.HTTPError as exc:
        body = exc.read(1024 * 1024).decode("utf-8", "replace")
        print(f"HTTP {exc.code}: {body}")
        return 1
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
