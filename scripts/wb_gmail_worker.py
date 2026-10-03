from __future__ import annotations

import base64
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from decimal import Decimal
from email.utils import parseaddr
from io import BytesIO
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from openpyxl import load_workbook
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models import (
    AuditLog, Equipment, LoadWbMatch, ShiftMaster, VehicleAlias,
    WbImportBatch, WbMovement,
)
from app.services.reconcile import auto_reconcile
from app.services.time_context import TZ, now_local
from app.services.wb_mapping import find_wb_sheet, row_value, build_location_resolver, expected_movement_date

CONFIG_PATH = ROOT / "config" / "wb_gmail_config.json"
TOKEN_PATH = ROOT / "config" / "gmail_token.json"
LOG_DIR = ROOT / "logs" / "wb_gmail"
LOG_PATH = LOG_DIR / "worker.log"
STATUS_PATH = LOG_DIR / "status.json"
ARCHIVE_DIR = ROOT / "data" / "wb_email_archive"
QUARANTINE_DIR = ROOT / "data" / "wb_quarantine"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
ENGINE_ACTOR = "WB_GMAIL_ENGINE"

LOG_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("wb_gmail")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = RotatingFileHandler(LOG_PATH, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(sh)


def write_status(**kwargs):
    payload = {"updated_at": datetime.now(timezone.utc).isoformat(), **kwargs}
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(STATUS_PATH)


def load_config():
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"Missing configuration: {CONFIG_PATH}")
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    required = [
        "enabled", "poll_seconds", "gmail_query", "allowed_senders",
        "processed_label", "duplicate_label", "error_label",
        "review_required_label", "review_rows_label",
        "max_review_percent", "max_file_mb", "start_after_utc",
    ]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise RuntimeError("Missing config keys: " + ", ".join(missing))
    return cfg


def save_token(creds):
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")


def gmail_service():
    if not TOKEN_PATH.exists():
        raise RuntimeError("Gmail is not authorized. Run authorize_wb_gmail.bat once.")
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_token(creds)
    if not creds.valid:
        raise RuntimeError("Gmail token is invalid. Run authorize_wb_gmail.bat again.")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def ensure_labels(service, names):
    existing = service.users().labels().list(userId="me").execute().get("labels", [])
    by_name = {x["name"]: x["id"] for x in existing}
    result = {}
    for name in names:
        if name not in by_name:
            created = service.users().labels().create(
                userId="me",
                body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
            ).execute()
            by_name[name] = created["id"]
        result[name] = by_name[name]
    return result


def sender_allowed(address, rules):
    address = (address or "").strip().lower()
    if not rules:
        return False
    for raw in rules:
        rule = str(raw or "").strip().lower()
        if not rule:
            continue
        if rule.startswith("*@"):
            if address.endswith(rule[1:]):
                return True
        elif rule.startswith("@"):
            if address.endswith(rule):
                return True
        elif address == rule:
            return True
    return False


def subject_allowed(subject, keywords):
    words = [str(x).strip().lower() for x in (keywords or []) if str(x).strip()]
    if not words:
        return True
    s = (subject or "").lower()
    return any(w in s for w in words)


def header_value(message, name):
    for h in message.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def walk_parts(part):
    yield part
    for child in part.get("parts", []) or []:
        yield from walk_parts(child)


def xlsx_attachments(service, message):
    found = []
    for part in walk_parts(message.get("payload", {})):
        filename = (part.get("filename") or "").strip()
        if not filename.lower().endswith(".xlsx"):
            continue
        body = part.get("body", {}) or {}
        data = body.get("data")
        if not data and body.get("attachmentId"):
            data = service.users().messages().attachments().get(
                userId="me", messageId=message["id"], id=body["attachmentId"]
            ).execute().get("data")
        if not data:
            continue
        raw = base64.urlsafe_b64decode(data.encode("ascii"))
        found.append((filename, raw))
    return found


def safe_name(name):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "WB.xlsx").strip("._")
    return (cleaned or "WB.xlsx")[:180]


def norm_header(value):
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def norm_vehicle(value):
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def decimal_value(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except Exception:
        return None


def clock_value(value):
    if isinstance(value, datetime):
        return value.time().replace(tzinfo=None)
    if isinstance(value, dtime):
        return value.replace(tzinfo=None)
    if isinstance(value, (int, float)) and 0 <= float(value) < 1:
        sec = int(round(float(value) * 86400)) % 86400
        return dtime(sec // 3600, (sec % 3600) // 60, sec % 60)
    txt = str(value or "").strip()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
        try:
            return datetime.strptime(txt, fmt).time()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(txt).time()
    except Exception:
        return None


def date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    txt = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            pass
    return None


def shift_bounds(day, definition):
    start = datetime.combine(day, definition.start_time, TZ)
    end = datetime.combine(day, definition.end_time, TZ)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def wb_weigh_at(day, definition, clock):
    if not clock:
        return None
    start, end = shift_bounds(day, definition)
    stamp = datetime.combine(day, clock, TZ)
    if end.date() > day and stamp < start:
        stamp += timedelta(days=1)
    return stamp if start <= stamp < end else None


def find_header(ws):
    for rix, row in enumerate(ws.iter_rows(min_row=1, max_row=min(ws.max_row, 20), values_only=True), 1):
        cand = {norm_header(v): i for i, v in enumerate(row) if str(v or "").strip()}
        if "VEHICLENUMBER" in cand and ("GROSSWEIGHT" in cand or "NETWEIGHT" in cand):
            return rix, cand
    raise ValueError("WB headers not found. Expected Vehicle Number / Gross Weight / Net Weight.")


def col(headers, *names):
    for name in names:
        key = norm_header(name)
        if key in headers:
            return headers[key]
    return None


def infer_file_context(ws, header_row, idx):
    dates, shifts = set(), set()
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if not any(v not in (None, "") for v in row):
            continue
        vehicle = row[idx["vehicle"]] if idx["vehicle"] is not None and idx["vehicle"] < len(row) else None
        if not str(vehicle or "").strip():
            continue
        if idx["date"] is not None and idx["date"] < len(row):
            d = date_value(row[idx["date"]])
            if d:
                dates.add(d)
        if idx["shift"] is not None and idx["shift"] < len(row):
            raw = str(row[idx["shift"]] or "").strip().upper()
            if raw[:1] in {"A", "B", "C"}:
                shifts.add(raw[:1])
    if len(dates) != 1:
        raise ValueError(f"Expected exactly one Movement Date in the workbook; found {sorted(map(str, dates)) or 'none'}.")
    if len(shifts) != 1:
        raise ValueError(f"Expected exactly one Shift Code A/B/C in the workbook; found {sorted(shifts) or 'none'}.")
    return next(iter(dates)), next(iter(shifts))


def audit(db, action, entity, entity_id, detail):
    db.add(AuditLog(
        created_at=now_local(),
        actor=ENGINE_ACTOR,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=json.dumps(detail, default=str),
    ))


def archive_bytes(content, filename, day, shift, digest):
    folder = ARCHIVE_DIR / day.isoformat() / shift
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{digest[:10]}_{safe_name(filename)}"
    if not target.exists():
        target.write_bytes(content)
    return target


def quarantine_bytes(content, filename, reason):
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = QUARANTINE_DIR / f"{stamp}_{safe_name(filename)}"
    target.write_bytes(content)
    meta = target.with_suffix(target.suffix + ".error.txt")
    meta.write_text(reason, encoding="utf-8")
    return target


def ingest_xlsx(content, filename, cfg, message_id):
    max_bytes = int(float(cfg.get("max_file_mb", 15)) * 1024 * 1024)
    if len(content) > max_bytes:
        raise ValueError(f"Attachment exceeds {cfg['max_file_mb']} MB.")
    digest = hashlib.sha256(content).hexdigest()
    try:
        wb = load_workbook(BytesIO(content), data_only=True, read_only=True)
    except Exception as exc:
        raise ValueError("Unable to read XLSX file.") from exc
    with SessionLocal() as db:
        # Use the same DB-backed WB header mapping/sheet detection as the
        # working manual/base-server WB upload. This supports aliases,
        # duplicate headers and WB data living on a non-active worksheet.
        ws, header_row, idx, header_diag = find_wb_sheet(wb, db)
        operating_date, shift = infer_file_context(ws, header_row, idx)

        definition = db.get(ShiftMaster, shift)
        if not definition or not definition.active:
            raise ValueError(f"Shift {shift} is not active in Shift Master.")

        duplicate = db.scalar(select(WbImportBatch).where(
            WbImportBatch.operating_date == operating_date,
            WbImportBatch.shift == shift,
            WbImportBatch.file_hash == digest,
        ))
        if duplicate:
            archive = archive_bytes(content, filename, operating_date, shift, digest)
            return {
                "outcome": "DUPLICATE",
                "batch_id": duplicate.batch_id,
                "date": operating_date.isoformat(),
                "shift": shift,
                "valid": duplicate.valid_rows,
                "review": duplicate.review_rows,
                "archive": str(archive),
                "message": "Exact WB file already exists in SQL; no rows were inserted.",
            }

        eq = list(db.scalars(select(Equipment)))
        vehicle_map = {norm_vehicle(e.machine_id): e.machine_id for e in eq}
        vehicle_map.update({norm_vehicle(e.vehicle_no): e.machine_id for e in eq if e.vehicle_no})
        for alias in db.scalars(select(VehicleAlias).where(VehicleAlias.active)):
            vehicle_map[norm_vehicle(alias.alias)] = alias.machine_id
        location_resolver = build_location_resolver(db)

        batch = WbImportBatch(
            batch_id=str(uuid4()),
            operating_date=operating_date,
            shift=shift,
            file_name=filename or "WB.xlsx",
            file_hash=digest,
            status="PREVIEW",
            valid_rows=0,
            review_rows=0,
        )
        db.add(batch)
        db.flush()

        valid = review = 0
        total_net = Decimal("0")
        unmapped_vehicles = set()
        tolerance = Decimal(str(cfg.get("weight_tolerance_kg", 5)))

        for rno, row in enumerate(ws.iter_rows(min_row=header_row + 1, values_only=True), header_row + 1):
            if not any(v not in (None, "") for v in row):
                continue

            def value(key):
                return row_value(row, idx, key)

            vehicle_raw = str(value("vehicle") or "").strip()
            if not vehicle_raw:
                continue

            issues = []
            warnings = []
            move = str(value("move") or rno).strip()
            row_day = date_value(value("date"))
            raw_shift = str(value("shift") or "").strip().upper()[:1]

            if raw_shift != shift:
                issues.append(f"Shift {raw_shift or '?'} != file shift {shift}")

            clock = clock_value(value("time"))
            weigh_at = wb_weigh_at(operating_date, definition, clock)
            if not weigh_at:
                issues.append("Invalid or out-of-shift GW Created Time")
            else:
                expected_day = expected_movement_date(operating_date, clock, definition)
                if row_day and expected_day and row_day != expected_day:
                    issues.append(
                        f"Movement Date {row_day} != expected calendar date {expected_day} "
                        f"for operating date {operating_date} / Shift {shift}"
                    )

            tare = decimal_value(value("tare"))
            gross = decimal_value(value("gross"))
            net = decimal_value(value("net"))
            tare = tare if tare is not None else Decimal("0")
            if gross is None and net is not None:
                gross = tare + net
            if net is None and gross is not None and gross >= tare:
                net = gross - tare
            gross = gross if gross is not None else Decimal("0")
            if gross <= 0 or net is None or net <= 0 or gross < tare:
                issues.append("Invalid tare/gross/net weight")
            elif abs((gross - tare) - net) > tolerance:
                issues.append(f"Gross-Tare differs from Net by more than {tolerance} kg")

            source = location_resolver.resolve(
                value("source_code"), value("source_name"), "SOURCE"
            )
            dest = location_resolver.resolve(
                value("dest_code"), value("dest_name"), "DESTINATION"
            )
            if not source:
                issues.append("Source location missing")
            if not dest:
                issues.append("Destination location missing")

            vehicle_id = vehicle_map.get(norm_vehicle(vehicle_raw))
            if not vehicle_id:
                unmapped_vehicles.add(vehicle_raw)
                warnings.append("Vehicle not mapped to equipment master")

            status = "REVIEW" if issues else "VALID"
            issue_text = "; ".join(issues + warnings) or None
            key = f"{batch.batch_id}:{move}:{rno}"
            db.add(WbMovement(
                movement_key=key,
                batch_id=batch.batch_id,
                operating_date=operating_date,
                shift=shift,
                movement_no=move,
                vehicle_raw=vehicle_raw,
                vehicle_id=vehicle_id,
                material_code=str(value("matcode") or "").strip() or None,
                material_name=str(value("matname") or "").strip() or None,
                source_raw=source or None,
                destination_raw=dest or None,
                tare_kg=tare,
                gross_kg=gross,
                net_kg=net or Decimal("0"),
                weigh_at=weigh_at or datetime.combine(operating_date, definition.start_time, TZ),
                row_status=status,
                issue=issue_text,
            ))
            if status == "VALID":
                valid += 1
                total_net += net or Decimal("0")
            else:
                review += 1

        if valid + review == 0:
            db.rollback()
            raise ValueError("No WB movement rows were found in the attachment.")

        batch.valid_rows = valid
        batch.review_rows = review
        review_pct = (review * 100.0 / (valid + review)) if (valid + review) else 100.0

        audit(db, "WB_EMAIL_PREVIEW", "wb_import_batch", batch.batch_id, {
            "gmail_message_id": message_id,
            "file": filename,
            "file_hash": digest,
            "date": operating_date,
            "shift": shift,
            "valid": valid,
            "review": review,
            "review_percent": round(review_pct, 2),
            "unmapped_vehicles": sorted(unmapped_vehicles),
            "sheet": ws.title,
            "header_mappings": header_diag.get("matched", {}),
            "duplicate_headers": header_diag.get("duplicates", {}),
        })

        archive = archive_bytes(content, filename, operating_date, shift, digest)

        max_review = float(cfg.get("max_review_percent", 5.0))
        auto_confirm = bool(cfg.get("auto_confirm", True))
        if valid <= 0 or review_pct > max_review or not auto_confirm:
            db.commit()
            return {
                "outcome": "REVIEW_REQUIRED",
                "batch_id": batch.batch_id,
                "date": operating_date.isoformat(),
                "shift": shift,
                "valid": valid,
                "review": review,
                "review_percent": round(review_pct, 2),
                "tonnes": float(total_net / Decimal("1000")),
                "unmapped_vehicles": sorted(unmapped_vehicles),
                "archive": str(archive),
                "message": f"WB loaded as PREVIEW only: {valid} VALID / {review} REVIEW.",
            }

        # Atomic replacement: only once the incoming file has passed validation.
        prior = list(db.scalars(select(WbImportBatch).where(
            WbImportBatch.operating_date == operating_date,
            WbImportBatch.shift == shift,
            WbImportBatch.status == "CONFIRMED",
        )))
        for old in prior:
            keys = list(db.scalars(select(WbMovement.movement_key).where(WbMovement.batch_id == old.batch_id)))
            if keys:
                db.execute(delete(LoadWbMatch).where(LoadWbMatch.movement_key.in_(keys)))
            old.status = "REPLACED"

        batch.status = "CONFIRMED"
        batch.confirmed_at = now_local()
        db.flush()
        reconciliation = auto_reconcile(db, operating_date, shift)
        audit(db, "WB_EMAIL_CONFIRM", "wb_import_batch", batch.batch_id, {
            "gmail_message_id": message_id,
            "valid": valid,
            "review": review,
            "tonnes": float(total_net / Decimal("1000")),
            "reconciliation": reconciliation,
        })
        db.commit()
        return {
            "outcome": "CONFIRMED",
            "batch_id": batch.batch_id,
            "date": operating_date.isoformat(),
            "shift": shift,
            "valid": valid,
            "review": review,
            "review_percent": round(review_pct, 2),
            "tonnes": float(total_net / Decimal("1000")),
            "unmapped_vehicles": sorted(unmapped_vehicles),
            "archive": str(archive),
            "reconciliation": reconciliation,
            "message": (
                f"WB auto-confirmed: {valid} VALID / {review} REVIEW; "
                f"{reconciliation['matched']} matched, "
                f"{reconciliation['wb_unmatched']} WB unmatched."
            ),
        }


def apply_labels(service, message_id, add_ids, remove_ids=None):
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": list(dict.fromkeys(add_ids)), "removeLabelIds": list(dict.fromkeys(remove_ids or []))},
    ).execute()


def process_message(service, message, cfg, labels):
    sender_text = header_value(message, "From")
    sender = parseaddr(sender_text)[1].lower()
    subject = header_value(message, "Subject")

    if not sender_allowed(sender, cfg.get("allowed_senders", [])):
        logger.warning("Skipped message %s from unapproved sender %s", message["id"], sender or sender_text)
        return {"status": "SKIPPED_SENDER", "message_id": message["id"], "sender": sender}

    if not subject_allowed(subject, cfg.get("subject_keywords", [])):
        logger.info("Skipped message %s because subject did not match configured keywords", message["id"])
        return {"status": "SKIPPED_SUBJECT", "message_id": message["id"], "subject": subject}

    start_after = datetime.fromisoformat(str(cfg["start_after_utc"]).replace("Z", "+00:00"))
    internal = datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000, tz=timezone.utc)
    if internal < start_after:
        return {"status": "SKIPPED_OLD", "message_id": message["id"]}

    attachments = xlsx_attachments(service, message)
    if not attachments:
        return {"status": "SKIPPED_NO_XLSX", "message_id": message["id"]}

    results = []
    for filename, content in attachments:
        try:
            result = ingest_xlsx(content, filename, cfg, message["id"])
            logger.info("%s | %s | %s", message["id"], filename, result["message"])
            results.append(result)
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            q = quarantine_bytes(content, filename, reason)
            logger.exception("WB attachment failed: message=%s file=%s quarantine=%s", message["id"], filename, q)
            results.append({"outcome": "ERROR", "message": reason, "quarantine": str(q), "file": filename})

    outcomes = {r["outcome"] for r in results}
    add = []
    remove = []

    if "ERROR" in outcomes:
        add.append(labels[cfg["error_label"]])
    elif "REVIEW_REQUIRED" in outcomes:
        add.append(labels[cfg["review_required_label"]])
    elif outcomes == {"DUPLICATE"}:
        add.append(labels[cfg["duplicate_label"]])
        if cfg.get("archive_success", True):
            remove.extend(["INBOX", "UNREAD"])
    else:
        add.append(labels[cfg["processed_label"]])
        if any(int(r.get("review", 0)) > 0 for r in results):
            add.append(labels[cfg["review_rows_label"]])
        if cfg.get("archive_success", True):
            remove.extend(["INBOX", "UNREAD"])

    apply_labels(service, message["id"], add, remove)
    return {
        "status": "DONE",
        "message_id": message["id"],
        "sender": sender,
        "subject": subject,
        "results": results,
    }


def poll_once(service, cfg, labels):
    label_names = [
        cfg["processed_label"], cfg["duplicate_label"], cfg["error_label"],
        cfg["review_required_label"],
    ]
    exclusions = " ".join(f"-label:{name}" for name in label_names)
    query = (str(cfg.get("gmail_query", "has:attachment filename:xlsx")).strip() + " " + exclusions).strip()
    response = service.users().messages().list(userId="me", q=query, maxResults=int(cfg.get("max_messages_per_poll", 25))).execute()
    ids = [x["id"] for x in response.get("messages", [])]
    processed = []
    for message_id in reversed(ids):
        message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        result = process_message(service, message, cfg, labels)
        processed.append(result)
    return processed


def main():
    logger.info("NMTPL WB Gmail worker starting. Project root=%s", ROOT)
    consecutive_failures = 0
    while True:
        try:
            cfg = load_config()
            if not cfg.get("enabled", False):
                write_status(state="DISABLED", message="Set enabled=true in config after authorization.")
                time.sleep(max(30, int(cfg.get("poll_seconds", 180))))
                continue

            service = gmail_service()
            label_names = [
                cfg["processed_label"], cfg["duplicate_label"], cfg["error_label"],
                cfg["review_required_label"], cfg["review_rows_label"],
            ]
            labels = ensure_labels(service, label_names)
            results = poll_once(service, cfg, labels)
            consecutive_failures = 0

            counts = {}
            for r in results:
                key = r.get("status", "UNKNOWN")
                counts[key] = counts.get(key, 0) + 1
            write_status(
                state="RUNNING",
                last_poll=datetime.now(timezone.utc).isoformat(),
                messages_seen=len(results),
                counts=counts,
            )
            if results:
                logger.info("Poll complete: %s", counts)
            time.sleep(max(30, int(cfg.get("poll_seconds", 180))))
        except KeyboardInterrupt:
            logger.info("Worker stopped by keyboard interrupt.")
            write_status(state="STOPPED")
            return
        except Exception as exc:
            consecutive_failures += 1
            logger.exception("Worker poll failed")
            write_status(
                state="ERROR",
                error=f"{type(exc).__name__}: {exc}",
                consecutive_failures=consecutive_failures,
            )
            # Never hammer Gmail/DB during an outage.
            time.sleep(min(900, max(60, consecutive_failures * 60)))


if __name__ == "__main__":
    main()