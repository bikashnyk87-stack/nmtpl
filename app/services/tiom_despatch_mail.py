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

from sqlalchemy import DateTime, Integer, String, Text, select
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


def _gmail_query(senders):
    """Restrict Gmail search to approved senders before fetching full messages."""
    if not senders:
        return ""
    safe = sorted(e.lower() for e in senders if re.fullmatch(r"[a-z0-9_.+%-]+@[a-z0-9.-]+", e.lower()))
    if not safe:
        return ""
    return "after:2026/09/30 has:attachment -label:NMTPL_DESPATCH_PROCESSED {" + (
        " ".join("from:" + e for e in safe)
    ) + "}"


def gmail_scan(max_messages=25):
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
              "tripsInserted": 0, "imagesSaved": 0, "skipped": 0, "errors": []}
    with SessionLocal() as db:
        _seed_senders(db)
        senders = set(db.scalars(select(DespatchSender.email).where(DespatchSender.active.is_(True))).all())
        remaining = min(max_messages, 25)
        query = _gmail_query(senders)
        if not query:
            return result
        # One distinct label avoids repeatedly reading October attachments.
        label_name = "NMTPL_DESPATCH_PROCESSED"
        labels = service.users().labels().list(userId="me").execute().get("labels", [])
        label_id = next((x["id"] for x in labels if x["name"] == label_name), None)
        if not label_id:
            label_id = service.users().labels().create(
                userId="me", body={"name": label_name}
            ).execute()["id"]
        page = None
        while remaining:
            args = {"userId": "me", "q": query,
                    "maxResults": min(remaining, 25)}
            if page:
                args["pageToken"] = page
            listing = service.users().messages().list(**args).execute()
            items = listing.get("messages", [])
            if not items:
                break
            for entry in items:
                remaining -= 1
                msgid = entry["id"]
                result["messagesScanned"] += 1
                if db.get(DespatchEmailProcessed, msgid):
                    scanned_ids.append(msgid)
                    result["skipped"] += 1
                    continue
                msg = service.users().messages().get(userId="me", id=msgid, format="full").execute()
                headers = {x["name"].lower(): x.get("value", "") for x in msg.get("payload", {}).get("headers", [])}
                sender = parseaddr(headers.get("from", ""))[1].lower()
                if sender not in senders:
                    result["skipped"] += 1
                    continue
                imported = 0
                images = 0
                relevant = False
                for p in _parts(msg.get("payload", {})):
                    filename = (p.get("filename") or "").strip()
                    mime = (p.get("mimeType") or "").lower()
                    if not filename and mime not in {"image/jpeg", "image/png", "image/webp"}:
                        continue
                    fname = filename.lower()
                    if not (fname.endswith((".xlsx", ".csv", ".jpg", ".jpeg", ".png", ".webp")) or
                            mime in {"image/jpeg", "image/png", "image/webp"}):
                        continue
                    binary = _attachment(service, msgid, p)
                    if not binary or len(binary) > 12_000_000:
                        continue
                    if fname.endswith((".xlsx", ".csv")):
                        try:
                            info = _import_data(db, binary, filename, "DESPATCH_GMAIL_ENGINE")
                            if info.get("ok"):
                                imported += int(info["inserted"])
                                relevant = True
                        except ValueError:
                            continue  # Non-trip summary workbook: not authoritative E-Pass data.
                    elif len(binary) > 3000 and len(binary) <= 8_000_000 and mime in {"image/jpeg", "image/png", "image/webp"}:
                        digest = sha256(binary).hexdigest()
                        if not db.scalar(select(DespatchDocument.id).where(DespatchDocument.sha256 == digest)):
                            doc = DespatchDocument(id=uuid4().hex, report_date=_message_date(
                                headers.get("subject", "") + " " + filename),
                                filename=(filename or ("gmail-" + msgid + ".jpg"))[:255],
                                media_type=mime, sha256=digest, image_data=binary,
                                review_status="NEEDS_REVIEW")
                            db.add(doc)
                            images += 1
                            relevant = True
                db.add(DespatchEmailProcessed(message_id=msgid, sender=sender,
                    status="IMPORTED" if relevant else "NO_MATCHING_DATA",
                    details=f"Trips inserted={imported}; images={images}"))
                db.commit()
                scanned_ids.append(msgid)
                result["tripsInserted"] += imported
                result["imagesSaved"] += images
                if relevant:
                    result["messagesImported"] += 1
            if scanned_ids:
                # One batch request instead of one Gmail modification per email.
                service.users().messages().batchModify(
                    userId="me",
                    body={"ids": scanned_ids, "addLabelIds": [label_id]}
                ).execute()
            page = listing.get("nextPageToken")
            if not page:
                break
    return result
