"""Source-verified, idempotent correction for the confirmed TIOM 22-Nov A WB batch.

The old 05:00-13:00 window classified 31 genuine 13:xx movements as
REVIEW. The new effective-from-1-Oct window is 06:00-14:00. Their old
fallback weigh_at timestamps cannot be trusted; only the original
matching XLSX may supply the physical time. No file is reimported and no
movement is added, deleted, or reassigned.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
from hashlib import sha256
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import select

from app.db import SessionLocal
from app.models import WbImportBatch, WbMovement, ShiftMaster
from app.services.tiom_shift_schedule import definition_for_day
from app.services.wb_mapping import (
    ensure_wb_header_mapping, find_wb_sheet, row_value, norm_vehicle,
    validate_wb_operational_metadata,
)
from app.services.tiom_location_erp import canonicalize_wb_rows

REPAIR_DAY = date(2026, 11, 22)
REPAIR_SHIFT = "A"
OLD_TIME_ISSUE = "Invalid or out-of-shift GW Created Time"


def _confirm_source_and_revalidate(db, batch, original_bytes):
    """Validate every source row before changing any saved REVIEW movement."""
    from scripts import wb_gmail_worker as worker

    if batch.status != "CONFIRMED" or batch.operating_date != REPAIR_DAY or batch.shift != REPAIR_SHIFT:
        raise ValueError("Confirmed 22-Nov-2026 A batch required")
    if sha256(original_bytes).hexdigest() != batch.file_hash:
        raise ValueError("Source Excel SHA256 does not match confirmed batch")

    master = db.get(ShiftMaster, REPAIR_SHIFT)
    if not master or not master.active:
        raise ValueError("Active TIOM A shift master is missing")
    dated = definition_for_day(REPAIR_DAY, master)
    if (dated.start_time.hour, dated.end_time.hour) != (6, 14):
        raise ValueError("Oct-effective A shift 06:00-14:00 is not active")

    original = load_workbook(BytesIO(original_bytes), read_only=True, data_only=True)
    ensure_wb_header_mapping(db)
    sheet, header_row, idx, diag = find_wb_sheet(original, db)
    if diag.get("missing"):
        raise ValueError("WB source missing required mapped headers")

    saved_rows = list(db.scalars(select(WbMovement).where(WbMovement.batch_id == batch.batch_id)))
    saved = {w.movement_key: w for w in saved_rows}
    if len(saved_rows) != len(saved):
        raise ValueError("Duplicate WB movement keys in confirmed batch")

    proposed = []
    source_keys = set()
    for rno, row in enumerate(sheet.iter_rows(min_row=header_row + 1, values_only=True), header_row + 1):
        if not any(v not in (None, "") for v in row):
            continue
        move = str(row_value(row, idx, "move") or rno).strip()
        vehicle = str(row_value(row, idx, "vehicle") or "").strip()
        if not vehicle:
            raise ValueError(f"Source row {rno} has no vehicle")
        key = f"{batch.batch_id}:{move}:{rno}"
        if key in source_keys or key not in saved:
            raise ValueError(f"Source row identity mismatch, row={rno}")
        source_keys.add(key)
        old = saved[key]
        if norm_vehicle(vehicle) != norm_vehicle(old.vehicle_raw):
            raise ValueError(f"Vehicle mismatch for {move}")
        for field, stored in (("tare", old.tare_kg), ("gross", old.gross_kg), ("net", old.net_kg)):
            source_val = worker.decimal_value(row_value(row, idx, field))
            if source_val is None or abs(source_val - Decimal(stored)) > Decimal("0.01"):
                raise ValueError(f"Original {field} differs from confirmed WB row {move}")

        if old.row_status != "REVIEW":
            continue
        reason_parts = [part.strip() for part in (old.issue or "").split(";") if part.strip()]
        allowed = {OLD_TIME_ISSUE, "Vehicle not mapped to equipment master"}
        if OLD_TIME_ISSUE not in reason_parts or any(part not in allowed for part in reason_parts):
            continue  # unrelated reviews must remain unchanged

        clock = worker.clock_value(row_value(row, idx, "time"))
        row_day = worker.date_value(row_value(row, idx, "date"))
        raw_shift = str(row_value(row, idx, "shift") or "").strip().upper()
        stamp = worker.wb_weigh_at(REPAIR_DAY, dated, clock)
        errors, notes = validate_wb_operational_metadata(
            REPAIR_DAY, REPAIR_SHIFT, raw_shift, row_day, clock, dated
        )
        if stamp is None or errors or row_day != REPAIR_DAY or raw_shift != REPAIR_SHIFT:
            continue
        proposed.append((old, stamp, notes, reason_parts))

    # The complete source file must correspond exactly to this confirmed batch,
    # not a summary tab or truncated/cross-shift subset.
    if len(source_keys) != len(saved):
        raise ValueError(f"Source row count {len(source_keys)} differs from saved {len(saved)}")

    if not proposed:
        return {"revalidated": 0, "valid": int(batch.valid_rows or 0),
                "review": int(batch.review_rows or 0), "state": "NO_ELIGIBLE_REVIEW"}

    before_counts = Counter(w.row_status for w in saved_rows)
    for w, stamp, notes, reasons in proposed:
        old_issue = w.issue
        old_stamp = w.weigh_at
        w.weigh_at = stamp
        w.row_status = "VALID"
        # Preserve nonblocking advisories without leaving a false REVIEW issue.
        w.issue = "; ".join([x for x in reasons if x != OLD_TIME_ISSUE] + notes) or None
        worker.audit(db, "TIOM_WB_SOURCE_TIME_REVALIDATED", "wb_movement", w.movement_key, {
            "source_sha256": batch.file_hash,
            "operating_date": REPAIR_DAY.isoformat(),
            "shift": REPAIR_SHIFT,
            "movement_no": w.movement_no,
            "original_issue": old_issue,
            "old_fallback_time": str(old_stamp),
            "verified_gw_time": stamp.isoformat(),
            "new_issue": w.issue,
        })

    db.flush()
    canonicalize_wb_rows(db, [entry[0] for entry in proposed])
    after_counts = Counter(w.row_status for w in saved_rows)
    if sum(after_counts.values()) != len(saved) or before_counts["REVIEW"] - after_counts["REVIEW"] != len(proposed):
        raise ValueError("WB batch validation counts inconsistent")
    batch.valid_rows = after_counts["VALID"]
    batch.review_rows = after_counts["REVIEW"]
    worker.audit(db, "TIOM_WB_CONFIRMED_REVALIDATED", "wb_import_batch", batch.batch_id, {
        "date": REPAIR_DAY.isoformat(), "shift": REPAIR_SHIFT,
        "source_sha256": batch.file_hash, "sheet": sheet.title,
        "before": dict(before_counts), "after": dict(after_counts),
        "revalidated": len(proposed),
    })
    db.commit()
    return {"state": "UPDATED", "revalidated": len(proposed),
            "valid": batch.valid_rows, "review": batch.review_rows,
            "batch_id": batch.batch_id, "source_verified": True}


def repair_22nov_a_confirmed_from_gmail():
    """Run once after startup; obtain the *identical* confirmed XLSX via Gmail.

    Requires a valid MIS Gmail OAuth token. A changed attachment or an
    inaccessible source is a hard stop, not an excuse to promote REVIEW rows.
    """
    from app.routers.automation import _prepare_gmail_token
    from scripts import wb_gmail_worker as worker

    with SessionLocal() as db:
        batch = db.scalar(select(WbImportBatch).where(
            WbImportBatch.operating_date == REPAIR_DAY,
            WbImportBatch.shift == REPAIR_SHIFT,
            WbImportBatch.status == "CONFIRMED",
        ).order_by(WbImportBatch.confirmed_at.desc()).limit(1))
        if not batch:
            return {"state": "NO_CONFIRMED_BATCH"}
        if not batch.review_rows:
            return {"state": "ALREADY_CLEAN", "valid": batch.valid_rows, "review": batch.review_rows}

        _prepare_gmail_token()
        service = worker.gmail_service()
        cfg = worker.load_config()
        authorized = cfg.get("allowed_senders", [])
        query = "has:attachment filename:xlsx after:2026/11/21 before:2026/11/24"
        # Keep the sender filter identical to the regular verified WB import.
        if authorized:
            query += " {" + " ".join("from:" + str(s) for s in authorized) + "}"
        response = service.users().messages().list(
            userId="me", q=query, maxResults=50
        ).execute()
        for entry in response.get("messages", []):
            message = service.users().messages().get(
                userId="me", id=entry["id"], format="full"
            ).execute()
            sender = worker.parseaddr(worker.header_value(message, "From"))[1].lower()
            if not worker.sender_allowed(sender, authorized):
                continue
            for filename, content in worker.xlsx_attachments(service, message):
                if sha256(content).hexdigest() == batch.file_hash:
                    result = _confirm_source_and_revalidate(db, batch, content)
                    result["message_id"] = entry["id"]
                    result["file_name"] = filename
                    return result
        return {"state": "SOURCE_NOT_FOUND", "expected_sha256": batch.file_hash}
