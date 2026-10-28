"""Independent TIOM despatch Gmail ingestion using the existing MIS Gmail OAuth token.

Never changes the weighbridge import labels, mappings or WB confirmation status.
"""
from __future__ import annotations

import base64
import logging
import re
from datetime import date, datetime
from email.utils import parseaddr
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text, LargeBinary, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base, SessionLocal
from app.routers.tiom_despatch import (
    DespatchAudit, DespatchDocument, DespatchSender, _import_data,
    _seed_senders,
)

log = logging.getLogger("nmtpl.despatch.gmail")


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
    report_date: Mapped[date | None] = mapped_column(DateTime, nullable=True)
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
    label_filter = ("label:NMTPL_DESPATCH_PROCESSED" if recovery else
                    "-label:NMTPL_DESPATCH_PROCESSED -label:NMTPL_DESPATCH_REVIEW_REQUIRED")
    return "after:2026/09/30 has:attachment " + label_filter + " {" + (
        " ".join("from:" + e for e in safe)
    ) + "}"


def _archive_for_review(db, msgid, sender, filename, binary, reason, report_date=None):
    """Retain the exact Excel bytes, never derive E-Pass trips from aggregates."""
    digest = sha256(binary).hexdigest()
    existing = db.scalar(select(DespatchMailAttachment.id).where(
        DespatchMailAttachment.message_id == msgid,
        DespatchMailAttachment.sha256 == digest
    ))
    if existing:
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


def _scan_message(service, db, msgid, senders, result, *, recovery=False):
    existing = db.get(DespatchEmailProcessed, msgid)
    if existing and not (recovery and existing.status == "NO_MATCHING_DATA"):
        return None
    msg = service.users().messages().get(userId="me", id=msgid, format="full").execute()
    headers = {x["name"].lower(): x.get("value", "") for x in msg.get("payload", {}).get("headers", [])}
    sender = parseaddr(headers.get("from", ""))[1].lower()
    if sender not in senders:
        result["skipped"] += 1
        return None
    imported, images, pending, matched = 0, 0, 0, False
    reasons = []
    date_guess = _message_date(headers.get("subject", ""))
    for part in _parts(msg.get("payload", {})):
        filename = (part.get("filename") or "").strip()
        mime = (part.get("mimeType") or "").lower()
        low = filename.lower()
        if not low and mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        spreadsheet = low.endswith((".xls", ".xlsx", ".csv"))
        img = low.endswith((".jpg", ".jpeg", ".png", ".webp")) or mime in {
            "image/jpeg", "image/png", "image/webp"
        }
        if not (spreadsheet or img):
            continue
        binary = _attachment(service, msgid, part)
        if not binary or len(binary) > 12_000_000:
            reasons.append(filename + ": missing attachment or file larger than 12 MB")
            continue
        if spreadsheet:
            try:
                info = _import_data(db, binary, filename, "DESPATCH_GMAIL_ENGINE")
                if not info.get("ok"):
                    raise ValueError("E-Pass validation errors: " +
                                     str(info.get("errors", [])[:2]))
                imported += int(info.get("inserted", 0))
                matched = True   # Idempotent existing E-Passes count as valid match.
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
    details = ("Trips inserted=" + str(imported) + "; images=" + str(images) +
               "; spreadsheets for review=" + str(pending) + "; " +
               "; ".join(reasons)[:1200])
    if existing:
        existing.status, existing.details, existing.checked_at = status, details, datetime.utcnow()
    else:
        db.add(DespatchEmailProcessed(message_id=msgid, sender=sender,
                                     status=status, details=details))
    db.commit()
    result["tripsInserted"] += imported
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
              "tripsInserted": 0, "imagesSaved": 0, "skipped": 0,
              "attachmentsForReview": 0, "recoveredEmails": 0, "errors": []}
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
                            "addLabelIds": [label_ids["NMTPL_DESPATCH_PROCESSED"]]}
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
