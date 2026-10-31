from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from sqlalchemy import select

from fastapi import APIRouter, Header, HTTPException

from app.db import SessionLocal
from app.services.volvo_client import VolvoClient, VolvoError, credential
from app.services.volvo_store import collect as collect_volvo
from app.services.volvo_control import collection_enabled

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
    """Use cloud provisioned credentials, or a locally authorized PC token.

    A local OAuth file is the canonical input for scripts/wb_gmail_worker.py.
    Formerly the PC was forced to set a Render-only environment variable even
    when its authorized token already existed at config/gmail_token.json.
    Never log or return the credential content.
    """
    cloud = (
        os.getenv("GMAIL_TOKEN_JSON", "").strip()
        or _secret_file_text("gmail_token.json", "GMAIL_TOKEN_JSON")
    )
    if cloud:
        return cloud
    path = ROOT / "config" / "gmail_token.json"
    try:
        if path.is_file() and path.stat().st_size <= 65536:
            return path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        pass
    return ""


def _prepare_gmail_token() -> Path:
    raw = _gmail_token_raw()
    if not raw:
        raise RuntimeError(
            "MIS Gmail is not connected on this server. On the PC use Despatch Report > Mail & Image Imports > Connect MIS Gmail; on Render set GMAIL_TOKEN_JSON or its Secret File."
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

def despatch_gmail_once():
    """Separate dispatch importer; does not affect the WB Gmail process."""
    from app.services.tiom_despatch_mail import gmail_scan
    result = gmail_scan(25)
    logger.info("TIOM despatch Gmail poll complete counts=%s", {
        k: v for k, v in result.items() if k != "errors"
    })
    return result



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
    with SessionLocal() as status_db:
        if not collection_enabled(status_db):
            return {"ok": True, "state": "PAUSED", "message": "Volvo sync paused in Volvo tab"}
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

@router.post("/despatch-gmail")
def run_despatch_gmail(
    x_automation_key: str | None = Header(default=None, alias="X-Automation-Key"),
):
    _require_automation_key(x_automation_key)
    try:
        return despatch_gmail_once()
    except Exception as exc:
        logger.exception("TIOM despatch Gmail poll failed")
        raise HTTPException(503, f"Despatch Gmail automation failed: {exc}") from exc


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


IST = ZoneInfo("Asia/Kolkata")
# Shift C ends at 05:00 the next calendar day; A ends 13:00, B ends 21:00.
# Times below are cloud Gmail *search* windows, not operating shift starts.
WB_WINDOWS = ((5, "C", -1), (13, "A", 0), (21, "B", 0))
WB_SEARCH_MINUTES = 120
WB_RETRY_SECONDS = 900
DESPATCH_RETRY_SECONDS = 900


def wb_search_window(now: datetime) -> tuple[str, datetime.date, str] | None:
    """Return (window key, operating date, shift) for a 2-hour IST slot."""
    local = now.astimezone(IST)
    for hour, shift, day_offset in WB_WINDOWS:
        start = local.replace(hour=hour, minute=0, second=0, microsecond=0)
        if start <= local < start + timedelta(minutes=WB_SEARCH_MINUTES):
            operating_date = local.date() + timedelta(days=day_offset)
            return (f"{local.date()}:{shift}", operating_date, shift)
    return None


def confirmed_wb_shift(operating_date, shift: str) -> bool:
    # Indexed, bounded check. The importer is the source of truth:
    # an email 'seen' or a quarantined file is not a successful WB import.
    from app.models import WbImportBatch
    with SessionLocal() as db:
        return db.scalar(select(WbImportBatch.batch_id).where(
            WbImportBatch.operating_date == operating_date,
            WbImportBatch.shift == shift,
            WbImportBatch.status == "CONFIRMED",
            WbImportBatch.valid_rows > 0,
        ).limit(1)) is not None


def confirmed_despatch_day(operating_date) -> bool:
    # The report is considered found only once at least one dated E-Pass
    # trip has been imported. Mailbox success without dated data is not enough.
    from app.routers.tiom_despatch import DespatchTrip
    with SessionLocal() as db:
        return db.scalar(select(DespatchTrip.epass_no).where(
            DespatchTrip.report_date == operating_date
        ).limit(1)) is not None


async def automation_loop():
    """IST-window cloud polling; outside the windows makes NO Gmail DB calls.

    WB 05:00-07:00 for prior C, 13:00-15:00 for current A, 21:00-23:00
    for current B. Every 15 min until that shift is confirmed, max two hours.
    Despatch 06:00 onward for previous day's report, every 15 min until
    that date has E-Pass trips, then no more Despatch scans that day.
    """
    wb_checked: dict[str, float] = {}
    wb_done: set[str] = set()
    dispatch_checked: dict[str, float] = {}
    dispatch_done: set[str] = set()
    volvo_interval = max(1800, int(os.getenv("VOLVO_POLL_SECONDS", "1800")))
    volvo_due = 0.0
    gmail_missing_logged = False
    volvo_missing_logged = False
    await asyncio.sleep(5)
    logger.info("Cloud low-compute schedule started: WB 05/13/21 IST (2h cap), Despatch from 06 IST, Volvo %ds (pauseable)", volvo_interval)
    while True:
        local = datetime.now(IST)
        monotonic = time.monotonic()
        today_key = local.date().isoformat()
        # Retain only today's completion flags; restart rechecks confirmed data.
        wb_done = {x for x in wb_done if x.startswith(today_key + ":")}
        wb_checked = {k:v for k,v in wb_checked.items() if k.startswith(today_key + ":")}
        dispatch_done = {x for x in dispatch_done if x == today_key}
        dispatch_checked = {k:v for k,v in dispatch_checked.items() if k == today_key}
        window = wb_search_window(local)
        if window and os.getenv("WB_GMAIL_ENABLED", "true").strip().lower() not in {"0","no","off","false"}:
            key, operating_date, shift = window
            if key not in wb_done and monotonic >= wb_checked.get(key, -1) + WB_RETRY_SECONDS:
                wb_checked[key] = monotonic
                if _gmail_token_raw():
                    try:
                        if await asyncio.to_thread(confirmed_wb_shift, operating_date, shift):
                            wb_done.add(key)
                        else:
                            await asyncio.to_thread(gmail_once)
                            if await asyncio.to_thread(confirmed_wb_shift, operating_date, shift):
                                wb_done.add(key)
                                logger.info("WB %s %s confirmed; stopping this shift's Gmail polls", operating_date, shift)
                    except Exception:
                        logger.exception("Scheduled WB Gmail scan failed for %s shift %s", operating_date, shift)
                    gmail_missing_logged = False
                elif not gmail_missing_logged:
                    logger.warning("WB Gmail scheduled scan waiting for Gmail token")
                    gmail_missing_logged = True

        if local.hour >= 6 and today_key not in dispatch_done and monotonic >= dispatch_checked.get(today_key,-1) + DESPATCH_RETRY_SECONDS:
            if os.getenv("TIOM_DESPATCH_GMAIL_ENABLED", "true").strip().lower() not in {"0","no","off","false"}:
                dispatch_checked[today_key] = monotonic
                if _gmail_token_raw():
                    report_date = local.date() - timedelta(days=1)
                    try:
                        if await asyncio.to_thread(confirmed_despatch_day, report_date):
                            dispatch_done.add(today_key)
                        else:
                            await asyncio.to_thread(despatch_gmail_once)
                            if await asyncio.to_thread(confirmed_despatch_day, report_date):
                                dispatch_done.add(today_key)
                                logger.info("Despatch %s imported; stopping today's Gmail scans", report_date)
                    except Exception:
                        logger.exception("Scheduled Despatch Gmail scan failed for %s", report_date)

        if monotonic >= volvo_due:
            volvo_due = monotonic + volvo_interval
            # Cached flag avoids a Neon read every 30min while paused.
            with SessionLocal() as db:
                enabled = collection_enabled(db)
            if enabled:
                username, password = _volvo_credentials()
                if username and password:
                    try:
                        await asyncio.to_thread(volvo_once)
                        volvo_missing_logged = False
                    except Exception:
                        logger.exception("Scheduled Volvo collection failed")
                elif not volvo_missing_logged:
                    logger.warning("Volvo cloud collection waiting for API credentials")
                    volvo_missing_logged = True
        await asyncio.sleep(30)
