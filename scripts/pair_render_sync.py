from __future__ import annotations

import getpass
import http.cookiejar
import json
from pathlib import Path
import socket
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "render_sync_client.json"
DEFAULT_BASE_URL = "https://nmtpl-tiom-test.onrender.com"


def _post(opener, url: str, payload: dict):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-NMTPL-Request": "webapp",
            "User-Agent": "NMTPL-Base-PC-Sync/1.0",
        },
    )
    with opener.open(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    print("NMTPL Render -> Base PC sync pairing")
    base_url = input(f"Render URL [{DEFAULT_BASE_URL}]: ").strip() or DEFAULT_BASE_URL
    base_url = base_url.rstrip("/")
    login_id = input("TIOM administrator login: ").strip()
    password = getpass.getpass("TIOM administrator password: ")
    if not login_id or not password:
        print("Login and password are required.")
        return 2

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        _post(
            opener,
            base_url + "/api/web/login",
            {"loginId": login_id, "password": password, "name": "Administrator"},
        )
        pair = _post(
            opener,
            base_url + "/api/sync/pair",
            {"deviceName": socket.gethostname() or "NMTPL Base PC"},
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        print(f"Pairing failed: HTTP {exc.code}: {body}")
        return 1
    except Exception as exc:
        print(f"Pairing failed: {type(exc).__name__}: {exc}")
        return 1
    finally:
        password = ""

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(
            {
                "base_url": base_url,
                "device_id": pair["deviceId"],
                "token": pair["token"],
                "poll_seconds": 180,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Paired successfully. Config saved to {CONFIG_PATH}")
    print("The password was not saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
