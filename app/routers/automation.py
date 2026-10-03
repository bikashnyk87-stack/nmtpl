from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException

from app.db import SessionLocal
from app.services.volvo_client import VolvoClient, VolvoError, credential
from app.services.volvo_store import collect as collect_volvo

router = APIRouter(prefix="/api/automation", tags=["automation"])
logger = logging.getLogger("nmtpl.automation")
ROOT = Path(__file__).resolve().parents[2]
RENDER_SECRETS = Path("/etc/secrets")


def _require_automation_key(x_automation_key: str | None) -> None:
    expected = os.getenv("NMTPL_AUTOMATION_KEY", "")
    if not expected or not x_automation_key or not hmac.compare_digest(expected, x_automation_key):
        raise HTTPException(401, "Invalid automation key.")


def _split_env(name: str) -> list[str] | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def _secret_file_text(*names: str) -> str:
    for name in names:
        path = RENDER_SECRETS / name
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8-sig").strip()
        except OSError:
            continue
    return ""


def _secret_dotenv_values() -> dict[str, str]:
    raw = _secret_file_text(".env", "env", "nmtpl.env")
    out: dict[str, str] = {}
    if not raw:
        return out
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _gmail_token_raw() -> str:
    return (
        os.getenv("GMAIL_TOKEN_JSON", "").strip()
        or _secret_file_text("gmail_token.json", "GMAIL_TOKEN_JSON")
    )


def _prepare_gmail_token() -> Path:
    raw = _gmail_token_raw()
    if not raw:
        raise RuntimeError(
            "Gmail token is not configured. Set GMAIL_TOKEN_JSON or add Render Secret File gmail_token.json."
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gmail token JSON is invalid.") from exc
    if not isinstance(payload, dict) or not payload.get("refresh_token"):
        raise RuntimeError("Gmail token JSON does not contain a refresh token.")

    path = ROOT / "config" / "gmail_token.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def _gmail_config(worker):
    cfg = worker.load_config()
    cfg["enabled"] = os.getenv("WB_GMAIL_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}

    senders = _split_env("WB_GMAIL_ALLOWED_SENDERS")
    if senders is not None:
        cfg["allowed_senders"] = [x.lower() for x in senders]

    subjects = _split_env("WB_GMAIL_SUBJECT_KEYWORDS")
    if subjects is not None:
        cfg["subject_keywords"] = subjects

    if os.getenv("WB_GMAIL_MAX_REVIEW_PERCENT"):
        cfg["max_review_percent"] = float(os.environ["WB_GMAIL_MAX_REVIEW_PERCENT"])
    if os.getenv("WB_GMAIL_MAX_MESSAGES"):
        cfg["max_messages_per_poll"] = int(os.environ["WB_GMAIL_MAX_MESSAGES"])
    return cfg


def gmail_once():
    _prepare_gmail_token()
    from scripts import wb_gmail_worker as worker

    cfg = _gmail_config(worker)
    if not cfg.get("enabled"):
        worker.write_status(state="DISABLED", message="WB_GMAIL_ENABLED is false.")
        return {"ok": True, "state": "DISABLED", "messages_seen": 0, "counts": {}}
    if not cfg.get("allowed_senders"):
        raise RuntimeError("No WB Gmail approved sender is configured.")

    service = worker.gmail_service()
    label_names = [
        cfg["processed_label"],
        cfg["duplicate_label"],
        cfg["error_label"],
        cfg["review_required_label"],
        cfg["review_rows_label"],
    ]
    labels = worker.ensure_labels(service, label_names)
    results = []
    retry_message_id = os.getenv("WB_GMAIL_RETRY_MESSAGE_ID", "").strip()
    if retry_message_id:
        message = service.users().messages().get(
            userId="me", id=retry_message_id, format="full"
        ).execute()
        retry_result = worker.process_message(service, message, cfg, labels)
        results.append(retry_result)
        logger.info("Targeted WB Gmail retry completed message=%s status=%s",
                    retry_message_id, retry_result.get("status"))
    results.extend(worker.poll_once(service, cfg, labels))
    counts = {}
    for item in results:
        key = item.get("status", "UNKNOWN")
        counts[key] = counts.get(key, 0) + 1

    worker.write_status(
        state="RUNNING",
        last_poll=worker.datetime.now(worker.timezone.utc).isoformat(),
        messages_seen=len(results),
        counts=counts,
    )
    logger.info("WB Gmail cloud poll complete messages=%s counts=%s", len(results), counts)
    return {"ok": True, "state": "RUNNING", "messages_seen": len(results), "counts": counts}


def _volvo_credentials() -> tuple[str, str]:
    secret_env = _secret_dotenv_values()
    username = (
        credential("VOLVO_API_USERNAME")
        or credential("VOLVO_USERNAME")
        or credential("VOLVO_USER")
        or secret_env.get("VOLVO_API_USERNAME", "")
        or secret_env.get("VOLVO_USERNAME", "")
        or secret_env.get("VOLVO_USER", "")
    )
    password = (
        credential("VOLVO_API_PASSWORD")
        or credential("VOLVO_PASSWORD")
        or credential("VOLVO_PASS")
        or secret_env.get("VOLVO_API_PASSWORD", "")
        or secret_env.get("VOLVO_PASSWORD", "")
        or secret_env.get("VOLVO_PASS", "")
    )
    base_url = (
        os.getenv("VOLVO_API_BASE_URL", "").strip()
        or secret_env.get("VOLVO_API_BASE_URL", "").strip()
    )
    if base_url and not os.getenv("VOLVO_API_BASE_URL"):
        os.environ["VOLVO_API_BASE_URL"] = base_url
    return username, password


def volvo_once():
    username, password = _volvo_credentials()
    if not username or not password:
        raise RuntimeError(
            "Volvo API credentials are not configured. Set Render environment variables or add a Secret File named .env."
        )

    with SessionLocal() as db:
        try:
            counts = collect_volvo(db, VolvoClient(username, password))
            logger.info("Volvo cloud sync complete counts=%s", counts)
            return {"ok": True, "counts": counts}
        except Exception:
            db.rollback()
            raise


@router.post("/gmail")
def run_gmail(
    x_automation_key: str | None = Header(default=None, alias="X-Automation-Key"),
):
    _require_automation_key(x_automation_key)
    try:
        return gmail_once()
    except Exception as exc:
        logger.exception("WB Gmail cloud poll failed")
        try:
            from scripts import wb_gmail_worker as worker
            worker.write_status(state="ERROR", error=f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
        raise HTTPException(503, f"WB Gmail automation failed: {exc}") from exc


@router.post("/volvo")
def run_volvo(
    x_automation_key: str | None = Header(default=None, alias="X-Automation-Key"),
):
    _require_automation_key(x_automation_key)
    try:
        return volvo_once()
    except VolvoError as exc:
        logger.warning("Volvo cloud sync failed: %s", exc)
        raise HTTPException(503, f"Volvo automation failed: {exc}") from exc
    except Exception as exc:
        logger.exception("Volvo cloud sync failed")
        raise HTTPException(503, f"Volvo automation failed: {exc}") from exc


async def automation_loop():
    """Zero-cost Render test loop.

    Runs inside the single web-service instance. It restarts automatically with
    the Render service. On Render free tier it pauses when the web service sleeps.
    """
    gmail_interval = max(60, int(os.getenv("WB_GMAIL_POLL_SECONDS", "180")))
    volvo_interval = max(60, int(os.getenv("VOLVO_POLL_SECONDS", "300")))
    gmail_due = 0.0
    volvo_due = 0.0
    gmail_missing_logged = False
    volvo_missing_logged = False

    await asyncio.sleep(5)
    logger.info(
        "Cloud automation loop started gmail_interval=%ss volvo_interval=%ss",
        gmail_interval,
        volvo_interval,
    )

    while True:
        now = time.monotonic()

        if now >= gmail_due:
            gmail_due = now + gmail_interval
            if _gmail_token_raw():
                try:
                    await asyncio.to_thread(gmail_once)
                    gmail_missing_logged = False
                except Exception:
                    logger.exception("Automatic WB Gmail poll failed")
            elif not gmail_missing_logged:
                logger.warning("WB Gmail auto-poll waiting for Gmail token environment variable or Secret File")
                gmail_missing_logged = True

        if now >= volvo_due:
            volvo_due = now + volvo_interval
            username, password = _volvo_credentials()
            if username and password:
                try:
                    await asyncio.to_thread(volvo_once)
                    volvo_missing_logged = False
                except Exception:
                    logger.exception("Automatic Volvo sync failed")
            elif not volvo_missing_logged:
                logger.warning("Volvo auto-sync waiting for Render Volvo API credentials or .env Secret File")
                volvo_missing_logged = True

        await asyncio.sleep(15)
