"""Independent TIOM despatch Gmail ingestion using the existing MIS Gmail OAuth token.

Never changes the weighbridge import labels, mappings or WB confirmation status.
"""
from __future__ import annotations

import base64
import logging
import re
from datetime import date, datetime
from threading import Lock
from email.utils import parseaddr
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import Date, DateTime, Integer, String, Text, LargeBinary, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base, SessionLocal
from app.routers.tiom_despatch import (
    DespatchAudit, DespatchDocument, DespatchSender, _import_data,
    _seed_senders,
)

log = logging.getLogger("nmtpl.despatch.gmail")
_ARCHIVE_VERSION = "[scope-20261027-v5]"
# Data through 26 Oct 2026 is already accepted by the site. Do not rescan
# or modify historical Despatch records unless a separate explicit correction
# workflow is requested.
DESPATCH_OPEN_FROM = date(2026, 10, 27)
_ARCHIVE_LOCK = Lock()


class DespatchEmailProcessed(Base):
    __tablename__ = "tiom_despatch_email_processed"
    message_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sender: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30))
    details: Mapped[str] = mapped_column(Text, default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DespatchMailAttachment(Base):
    """Original approved MIS spreadsheets kept for review, never guessed as trips."""
    __tablename__ = "tiom_despatch_mail_attachment"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(128), index=True)
    sender: Mapped[str] = mapped_column(String(200))
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    file_data: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(40), default="REVIEW_REQUIRED")
    reason: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DespatchMailPoll(Base):
    """Persistent evidence of automatic/manual MIS mailbox sync attempts."""
    __tablename__ = "tiom_despatch_mail_poll"
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    last_attempt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_result: Mapped[str] = mapped_column(Text, default="{}")


def _save_poll(stage, result=None, error=""):
    import json
    from datetime import timezone
    with SessionLocal() as db:
        item=db.get(DespatchMailPoll, "MIS")
        if item is None:
            item=DespatchMailPoll(id="MIS")
            db.add(item)
        now=datetime.now(timezone.utc)
        if stage=="STARTED":
            item.last_attempt=now
            item.last_error=""
        elif stage=="SUCCESS":
            item.last_success=now
            item.last_error=""
            item.last_result=json.dumps(result or {})
        elif stage=="ERROR":
            item.last_error=str(error)[:400]
        db.commit()


def _message_date(text):
    for match in re.finditer(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](20\d{2}|\d{2})(?!\d)", text or ""):
        d, m, y = (int(part) for part in match.groups())
        if y < 100:
            y += 2000
        try:
            return date(y, m, d)
        except ValueError:
            continue
    return None


def is_open_despatch_source(attachment):
    """Use report date, then the archived attachment's filename date.

    Review files without a verified report date are retained in storage, but
    not represented as new daily exceptions until a date is confirmed.
    """
    source_day = attachment.report_date or _message_date(attachment.filename)
    return source_day is not None and source_day >= DESPATCH_OPEN_FROM


def open_despatch_reviews(db):
    """Current reporting window only. Read-only, does not delete history."""
    return [
        item for item in db.scalars(select(DespatchMailAttachment).where(
            DespatchMailAttachment.status == "REVIEW_REQUIRED"
        ).order_by(DespatchMailAttachment.message_id, DespatchMailAttachment.received_at))
        if is_open_despatch_source(item)
    ]


def _parts(part):
    if part.get("filename") or part.get("body", {}).get("attachmentId"):
        yield part
    for child in part.get("parts", ()) or ():
        yield from _parts(child)


def _attachment(service, msgid, item):
    body = item.get("body", {}) or {}
    encoded = body.get("data")
    if not encoded and body.get("attachmentId"):
        encoded = service.users().messages().attachments().get(
            userId="me", messageId=msgid, id=body["attachmentId"]
        ).execute().get("data", "")
    if not encoded:
        return b""
    return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))


def _gmail_query(senders, *, recovery=False):
    """Only approved sender attachments, but allow recovery of mislabelled mail."""
    if not senders:
        return ""
    safe = sorted(e.lower() for e in senders if re.fullmatch(r"[a-z0-9_.+%-]+@[a-z0-9.-]+", e.lower()))
    if not safe:
        return ""
    # REVIEW_REQUIRED attachments are rechecked from their stored original bytes.
    # Do not repeatedly re-download the same 25 Gmail review messages every poll.
    label_filter = ("label:NMTPL_DESPATCH_PROCESSED" if recovery else
                    "-label:NMTPL_DESPATCH_PROCESSED -label:NMTPL_DESPATCH_REVIEW_REQUIRED")
    return "after:2026/10/26 has:attachment " + label_filter + " {" + (
        " ".join("from:" + e for e in safe)
    ) + "}"


def _archive_for_review(db, msgid, sender, filename, binary, reason, report_date=None):
    """Retain the exact Excel bytes, never derive E-Pass trips from aggregates."""
    digest = sha256(binary).hexdigest()
    existing = db.scalar(select(DespatchMailAttachment).where(
        DespatchMailAttachment.message_id == msgid,
        DespatchMailAttachment.sha256 == digest
    ))
    if existing:
        if existing.status == "REVIEW_REQUIRED":
            existing.reason = str(reason)[:600]
            if report_date and not existing.report_date:
                existing.report_date = report_date
            return True
        return False
    mime = ("application/vnd.ms-excel" if filename.lower().endswith(".xls") else
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if filename.lower().endswith(".xlsx") else "text/csv")
    db.add(DespatchMailAttachment(
        id=uuid4().hex, message_id=msgid, sender=sender,
        filename=filename[:255], sha256=digest, mime_type=mime,
        file_data=binary, status="REVIEW_REQUIRED",
        reason=str(reason)[:600], report_date=report_date,
    ))
    return True


def recheck_archived_despatch(*, limit_messages=8, after="", force=False):
    """Reconcile stored Gmail XLS/XLSX/CSV without downloading/relabeling mail.

    Runs in bounded batches, keeps original attachments and verifies each file
    by the current parser against the canonical E-Pass ledger. Detailed sheets
    are ingested before complementary Transporter-wise sheets within an email.
    Only genuinely unresolved files remain in the review list. Rechecks each
    schema-version once; use force for operator-initiated recheck after changes.
    """
    from app.services.tiom_despatch_source_adapters import detect_source_type
    from sqlalchemy import func
    if not _ARCHIVE_LOCK.acquire(blocking=False):
        return {"ok": False, "busy": True, "processedMessages": 0,
                "resolvedFiles": 0, "remainingFiles": None, "nextCursor": None}
    try:
        limit_messages = max(1, min(int(limit_messages), 15))
        cursor = str(after or "")[:128]
        resolved_ids = []
        processed = resolved = outside = 0
        new_trips = enriched = 0
        problems = []
        with SessionLocal() as db:
            # Site-accepted records through 26-Oct are not a pending workload.
            # Filter using either metadata or the source filename. Never touch
            # old review rows or the canonical old trip ledger.
            eligible = [
                item for item in open_despatch_reviews(db)
                if item.message_id > cursor
                and (force or not item.reason.startswith(_ARCHIVE_VERSION))
            ]
            message_ids = sorted({item.message_id for item in eligible})
            targets = message_ids[:limit_messages]
            for msgid in targets:
                stored = [item for item in db.scalars(select(DespatchMailAttachment).where(
                    DespatchMailAttachment.message_id == msgid,
                    DespatchMailAttachment.status == "REVIEW_REQUIRED",
                ).order_by(DespatchMailAttachment.received_at)) if is_open_despatch_source(item)]
                prepared = []
                for attachment in stored:
                    try:
                        role = detect_source_type(attachment.file_data, attachment.filename)
                        priority = 0 if role == "detailed" else 1
                        preliminary_error = None
                    except (ValueError, UnicodeError) as exc:
                        priority = 2
                        preliminary_error = str(exc)
                    prepared.append((priority, attachment, preliminary_error))
                # Foreign/obsolete September files are retained, not shown as
                # active October failures; October remains the configured ledger.
                for _, attachment, preliminary_error in sorted(prepared, key=lambda x: x[0]):
                    filename_date = attachment.report_date or _message_date(attachment.filename)
                    if filename_date and filename_date < date(2026, 10, 1):
                        attachment.status = "OUT_OF_SCOPE"
                        attachment.reason = "Archived historical source; existing October ledger unchanged"
                        outside += 1
                        db.commit()
                        continue
                    try:
                        if preliminary_error:
                            raise ValueError(preliminary_error)
                        info = _import_data(db, attachment.file_data, attachment.filename,
                                            "DESPATCH_ARCHIVE_RECHECK")
                        if not info.get("ok"):
                            errors = info.get("errors") or []
                            reason = "; ".join(str(x.get("error", "")) for x in errors[:2])
                            raise ValueError(reason or "Cannot reconcile source E-Passes")
                        attachment.status = "IMPORTED"
                        attachment.reason = "Verified against E-Pass ledger using current source adapter"
                        resolved += 1
                        new_trips += int(info.get("inserted", 0))
                        enriched += int(info.get("enriched", 0))
                    except (ValueError, UnicodeError) as exc:
                        attachment.reason = (_ARCHIVE_VERSION + " " + str(exc))[:600]
                        if len(problems) < 12:
                            problems.append({"file": attachment.filename, "reason": str(exc)[:180]})
                    # Commit each file status independently: a later manifest
                    # conflict can roll back its own upsert without reverting
                    # the review status of an earlier successful weighment.
                    db.commit()
                remaining_message = db.scalar(select(DespatchMailAttachment.id).where(
                    DespatchMailAttachment.message_id == msgid,
                    DespatchMailAttachment.status == "REVIEW_REQUIRED",
                ).limit(1))
                if not remaining_message:
                    audited = db.get(DespatchEmailProcessed, msgid)
                    if audited and audited.status in {"REVIEW_REQUIRED", "NO_MATCHING_DATA", "IMPORTED_WITH_REVIEW"}:
                        audited.status = "IMPORTED"
                        audited.details = "All archived approved-sender spreadsheets reconciled or archived outside date scope"
                        audited.checked_at = datetime.utcnow()
                        db.commit()
                    resolved_ids.append(msgid)
                processed += 1
            remaining_files = len(open_despatch_reviews(db))
        return {"ok": True, "processedMessages": processed,
                "resolvedFiles": resolved, "historicalFilesArchived": outside,
                "tripsInserted": new_trips, "transporterEntriesEnriched": enriched,
                "remainingFiles": remaining_files,
                "nextCursor": targets[-1] if targets and len(message_ids) > len(targets) else None,
                "resolvedMessageIds": resolved_ids, "errors": problems}
    finally:
        _ARCHIVE_LOCK.release()


def _scan_message(service, db, msgid, senders, result, *, recovery=False):
    """A single Gmail message can supply complementary weighment/manifests.

    Detect each spreadsheet layout before processing so the detailed source
    commits first and transporter rows can reconcile against its E-Pass IDs.
    """
    from app.services.tiom_despatch_source_adapters import detect_source_type
    existing = db.get(DespatchEmailProcessed, msgid)
    if existing and not (recovery and existing.status == "NO_MATCHING_DATA"):
        return None
    msg = service.users().messages().get(userId="me", id=msgid, format="full").execute()
    headers = {x["name"].lower(): x.get("value", "") for x in msg.get("payload", {}).get("headers", [])}
    sender = parseaddr(headers.get("from", ""))[1].lower()
    if sender not in senders:
        result["skipped"] += 1
        return None

    imported, enriched, images, pending, matched = 0, 0, 0, 0, False
    reasons = []
    date_guess = _message_date(headers.get("subject", ""))
    if date_guess is not None and date_guess < DESPATCH_OPEN_FROM:
        # 1–26 October is already accepted by site. Never reimport it from Gmail.
        result["skipped"] += 1
        return None
    candidates = []
    for part in _parts(msg.get("payload", {})):
        filename = (part.get("filename") or "").strip()
        mime = (part.get("mimeType") or "").lower()
        name = filename.lower()
        spreadsheet = name.endswith((".xls", ".xlsx", ".csv"))
        is_image = name.endswith((".jpg", ".jpeg", ".png", ".webp")) or mime in {
            "image/jpeg", "image/png", "image/webp"
        }
        if not (spreadsheet or is_image):
            continue
        binary = _attachment(service, msgid, part)
        if not binary or len(binary) > 12_000_000:
            reasons.append(filename + ": missing data or exceeds 12 MB")
            continue
        if spreadsheet:
            try:
                role = detect_source_type(binary, filename)
                priority = 0 if role == "detailed" else 1
            except ValueError:
                priority = 2
        else:
            priority = 3
        candidates.append((priority, filename, mime, binary, spreadsheet))
    for _, filename, mime, binary, spreadsheet in sorted(candidates, key=lambda x: x[0]):
        if spreadsheet:
            try:
                info = _import_data(db, binary, filename, "DESPATCH_GMAIL_ENGINE")
                if not info.get("ok"):
                    raise ValueError("E-Pass validation failed: " +
                                     str(info.get("errors", [])[:2]))
                imported += int(info.get("inserted", 0))
                enriched += int(info.get("enriched", 0))
                matched = True
                digest = sha256(binary).hexdigest()
                old_review = db.scalar(select(DespatchMailAttachment).where(
                    DespatchMailAttachment.message_id == msgid,
                    DespatchMailAttachment.sha256 == digest,
                ))
                if old_review:
                    old_review.status = "IMPORTED"
                    old_review.reason = "Mapped and reconciled by E-Pass number"
            except ValueError as exc:
                reason = str(exc)
                if _archive_for_review(db, msgid, sender, filename, binary, reason, date_guess):
                    pending += 1
                reasons.append(filename + ": " + reason)
        elif 3000 < len(binary) <= 8_000_000 and mime in {
            "image/jpeg", "image/png", "image/webp"
        }:
            digest = sha256(binary).hexdigest()
            if not db.scalar(select(DespatchDocument.id).where(DespatchDocument.sha256 == digest)):
                db.add(DespatchDocument(
                    id=uuid4().hex,
                    report_date=_message_date(headers.get("subject", "") + " " + filename),
                    filename=(filename or ("gmail-" + msgid + ".jpg"))[:255],
                    media_type=mime, sha256=digest, image_data=binary,
                    review_status="NEEDS_REVIEW"))
                images += 1
            matched = True
    status = ("IMPORTED_WITH_REVIEW" if matched and pending else
              "IMPORTED" if matched else "REVIEW_REQUIRED")
    details = ("Trips inserted=" + str(imported) + "; transporter entries enriched=" +
               str(enriched) + "; images=" + str(images) +
               "; spreadsheets for review=" + str(pending) + "; " +
               "; ".join(reasons)[:1200])
    if existing:
        existing.status, existing.details, existing.checked_at = status, details, datetime.utcnow()
    else:
        db.add(DespatchEmailProcessed(message_id=msgid, sender=sender,
                                     status=status, details=details))
    db.commit()
    result["tripsInserted"] += imported
    result["tripsEnriched"] = result.get("tripsEnriched", 0) + enriched
    result["imagesSaved"] += images
    result["attachmentsForReview"] += pending
    if matched:
        result["messagesImported"] += 1
    if recovery:
        result["recoveredEmails"] += 1
    return status


def _gmail_scan_actual(max_messages=25):
    from app.routers.automation import _prepare_gmail_token
    from scripts.wb_gmail_worker import gmail_service

    _prepare_gmail_token()
    service = gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    address = (profile.get("emailAddress") or "").lower().strip()
    if address != "mistiom@nmtpl.com":
        raise RuntimeError("Gmail OAuth authorizes " + (address or "(unknown)") +
                           ", not the MIS mailbox mistiom@nmtpl.com.")

    result = {"mailbox": address, "messagesScanned": 0, "messagesImported": 0,
              "tripsInserted": 0, "tripsEnriched": 0, "imagesSaved": 0, "skipped": 0,
              "attachmentsForReview": 0, "recoveredEmails": 0, "errors": []}
    # Process a bounded number of already-downloaded reviews on every regular
    # automatic Gmail poll. This does not need fresh Gmail attachment downloads,
    # and each item is attempted once per source-adapter version.
    archive_result = recheck_archived_despatch(limit_messages=5)
    result["archivedFilesReconciled"] = archive_result.get("resolvedFiles", 0)
    result["archivedTripsInserted"] = archive_result.get("tripsInserted", 0)
    result["archivedTransportersEnriched"] = archive_result.get("transporterEntriesEnriched", 0)
    result["tripsInserted"] += archive_result.get("tripsInserted", 0)
    result["tripsEnriched"] += archive_result.get("transporterEntriesEnriched", 0)
    with SessionLocal() as db:
        _seed_senders(db)
        senders = set(db.scalars(select(DespatchSender.email).where(
            DespatchSender.active.is_(True))).all())
        if not senders:
            return result
        labels = service.users().labels().list(userId="me").execute().get("labels", [])
        label_ids = {x["name"]: x["id"] for x in labels}
        for label in ("NMTPL_DESPATCH_PROCESSED", "NMTPL_DESPATCH_REVIEW_REQUIRED"):
            if label not in label_ids:
                label_ids[label] = service.users().labels().create(
                    userId="me", body={"name": label}
                ).execute()["id"]
        if archive_result.get("resolvedMessageIds"):
            try:
                service.users().messages().batchModify(
                    userId="me", body={
                        "ids": archive_result["resolvedMessageIds"],
                        "addLabelIds": [label_ids["NMTPL_DESPATCH_PROCESSED"]],
                        "removeLabelIds": [label_ids["NMTPL_DESPATCH_REVIEW_REQUIRED"]],
                    }
                ).execute()
            except Exception:
                log.warning("Archived E-Pass records reconciled; Gmail review label could not be updated", exc_info=True)
        for recovery in (False, True):
            if recovery and not db.scalar(select(DespatchEmailProcessed.message_id).where(
                DespatchEmailProcessed.status == "NO_MATCHING_DATA").limit(1)):
                break
            remaining = min(max(1, max_messages), 50)
            query = _gmail_query(senders, recovery=recovery)
            page = None
            while remaining:
                args = {"userId": "me", "q": query, "maxResults": min(remaining, 25)}
                if page:
                    args["pageToken"] = page
                listing = service.users().messages().list(**args).execute()
                items = listing.get("messages", [])
                if not items:
                    break
                processed_ids, review_ids = [], []
                for entry in items:
                    remaining -= 1
                    msgid = entry["id"]
                    status = _scan_message(service, db, msgid, senders, result, recovery=recovery)
                    if status is None:
                        result["skipped"] += 1
                        continue
                    result["messagesScanned"] += 1
                    if status in {"IMPORTED", "IMPORTED_WITH_REVIEW"}:
                        processed_ids.append(msgid)
                    else:
                        review_ids.append(msgid)
                if processed_ids:
                    service.users().messages().batchModify(
                        userId="me", body={"ids": processed_ids,
                            "addLabelIds": [label_ids["NMTPL_DESPATCH_PROCESSED"]],
                            "removeLabelIds": [label_ids["NMTPL_DESPATCH_REVIEW_REQUIRED"]]}
                    ).execute()
                if review_ids:
                    service.users().messages().batchModify(
                        userId="me", body={"ids": review_ids,
                            "addLabelIds": [label_ids["NMTPL_DESPATCH_REVIEW_REQUIRED"]],
                            "removeLabelIds": [label_ids["NMTPL_DESPATCH_PROCESSED"]]}
                    ).execute()
                page = listing.get("nextPageToken")
                if not page:
                    break
    # Apply only provable exact-permit categories from completed E-Pass records.
    # An unknown permit remains an explicit source-mapping exception; this
    # never changes 1–26 October or the daily weight/vehicle/permit ledger.
    try:
        from app.services.tiom_despatch_mapping import reconcile_known_permits
        with SessionLocal() as mapping_db:
            mapping = reconcile_known_permits(mapping_db)
        result["sourceCategoriesAutofilled"] = mapping["updatedTrips"]
    except Exception:
        log.exception("Automatic Despatch permit source reconciliation failed")
        result["sourceCategoriesAutofilled"] = 0
    # Reconcile newly received and previously stored AMNS images as part of
    # the existing scheduled Gmail scan. No new task or manual nightly steps.
    try:
        from app.services.tiom_despatch_amns import auto_process_pending_images
        amns = auto_process_pending_images(limit=3)
        result["amnsVerifiedImages"] = amns["verifiedImages"]
        result["amnsExceptions"] = amns["imagesNeedingReview"]
        result["amnsReconciled"] = amns["results"]
    except Exception:
        log.exception("AMNS automatic reconciliation failed; unchanged Despatch ledger")
        result["amnsVerifiedImages"] = 0
        result["amnsExceptions"] = 1
    return result


def gmail_scan(max_messages=25):
    """Audit every poll, including idle/empty ones and Gmail quota failures."""
    _save_poll("STARTED")
    try:
        report=_gmail_scan_actual(max_messages)
    except Exception as exc:
        _save_poll("ERROR",error=f"{type(exc).__name__}: {exc}")
        log.exception("Despatch MIS Gmail sync failed")
        raise
    _save_poll("SUCCESS",result=report)
    log.info("Despatch MIS Gmail poll succeeded: %s", report)
    return report
