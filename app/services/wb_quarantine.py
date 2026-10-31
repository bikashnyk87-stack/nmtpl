"""Durable, access-controlled archive of rejected WB Gmail XLSX files.

The previous quarantine was stored only on Render's ephemeral filesystem and
could disappear during a restart. Keep the original exact bytes in PostgreSQL
for management review; never silently re-import or confirm an invalid file.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base, SessionLocal


class WbGmailQuarantine(Base):
    __tablename__ = "wb_gmail_quarantine"
    file_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    gmail_message_id: Mapped[str] = mapped_column(String(128), index=True)
    sender: Mapped[str] = mapped_column(String(200))
    file_name: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text)
    file_size: Mapped[int] = mapped_column(Integer)
    file_data: Mapped[bytes] = mapped_column(LargeBinary)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


def store_rejected_attachment(
    gmail_message_id: str, sender: str, filename: str, content: bytes, reason: str
) -> str:
    """Idempotent by SHA-256. Raw data is not changed on repeated failures."""
    # No exceptionally large attachment may fill the Neon Free 1 GB quota.
    if len(content) > 12_000_000:
        raise ValueError("Rejected XLSX exceeds the 12 MB persistent archive limit.")
    digest = sha256(content).hexdigest()
    with SessionLocal.begin() as db:
        WbGmailQuarantine.__table__.create(bind=db.get_bind(), checkfirst=True)
        existing = db.get(WbGmailQuarantine, digest)
        if existing is None:
            db.add(WbGmailQuarantine(
                file_hash=digest,
                gmail_message_id=str(gmail_message_id)[:128],
                sender=str(sender or "")[:200],
                file_name=str(filename or "WB.xlsx")[:255],
                reason=str(reason)[:2000],
                file_size=len(content),
                file_data=content,
            ))
        else:
            existing.reason = str(reason)[:2000]
    return digest
