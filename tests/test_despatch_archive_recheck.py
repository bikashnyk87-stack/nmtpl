"""Historical approved Gmail reports must automatically exit the huge review list."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.routers import tiom_despatch as router
from app.services import tiom_despatch_mail as mail
from tests.test_despatch_multisource_dynamic import sample_datewise, sample_transporter


def _isolated_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = (
        router.DespatchTrip.__table__,
        router.DespatchAudit.__table__,
        mail.DespatchEmailProcessed.__table__,
        mail.DespatchMailAttachment.__table__,
    )
    Base.metadata.create_all(engine, tables=tables)
    maker = sessionmaker(bind=engine)
    monkeypatch.setattr(mail, "SessionLocal", maker)
    return maker


def _review(msgid, filename, data, date_value):
    return mail.DespatchMailAttachment(
        id=uuid.uuid4().hex, message_id=msgid,
        sender="rajugupta97093@gmail.com", filename=filename,
        sha256=uuid.uuid4().hex, file_data=data, mime_type="application/vnd.ms-excel",
        report_date=date_value, status="REVIEW_REQUIRED",
        reason="No dated E-Pass Trip Summary sheets found; old adapter"
    )


def test_old_datewise_and_transporter_reconciled_from_existing_archive(monkeypatch):
    maker = _isolated_db(monkeypatch)
    with maker() as db:
        db.add_all([
            _review("msg-27", "Date WIse 27-10-2026.xls", sample_datewise(), date(2026,10,27)),
            _review("msg-27", "Transporter WIse 27-10-2026.xls", sample_transporter(), date(2026,10,27)),
            mail.DespatchEmailProcessed(message_id="msg-27", sender="rajugupta97093@gmail.com",
                                       status="REVIEW_REQUIRED", details="Old format rejected"),
        ])
        db.commit()
    result = mail.recheck_archived_despatch(limit_messages=8)
    assert result["ok"] and result["processedMessages"] == 1
    assert result["resolvedFiles"] == 2 and result["tripsInserted"] == 2
    assert result["transporterEntriesEnriched"] == 2 and result["remainingFiles"] == 0
    with maker() as db:
        assert all(x.status == "IMPORTED" for x in db.scalars(select(mail.DespatchMailAttachment)))
        assert db.get(mail.DespatchEmailProcessed, "msg-27").status == "IMPORTED"
        trips = list(db.scalars(select(router.DespatchTrip)))
        assert len(trips) == 2
        assert sum(float(x.net_mt) for x in trips) == 63.83
        assert all(x.transporter == "RIDHICON LOGISTICS PRIVATE LIMITED" for x in trips)
        # idempotent: a second automatic recheck inserts no duplicates.
        second = mail.recheck_archived_despatch(limit_messages=8)
        assert second["processedMessages"] == 0 and second["tripsInserted"] == 0


def test_incomplete_source_keeps_fresh_actionable_reason_and_is_not_retried_forever(monkeypatch):
    maker = _isolated_db(monkeypatch)
    with maker() as db:
        db.add(_review("msg-bad", "Date Wise 27-10-2026.xls", b"not-a-workbook", date(2026,10,27)))
        db.commit()
    result = mail.recheck_archived_despatch()
    assert result["processedMessages"] == 1 and result["resolvedFiles"] == 0
    assert result["remainingFiles"] == 1
    with maker() as db:
        row = db.scalar(select(mail.DespatchMailAttachment))
        assert row.status == "REVIEW_REQUIRED"
        assert row.reason.startswith(mail._ARCHIVE_VERSION)
        assert "Unsupported Excel" in row.reason
    assert mail.recheck_archived_despatch()["processedMessages"] == 0
    assert mail.recheck_archived_despatch(force=True)["processedMessages"] == 1


def test_closed_period_sources_are_preserved_without_reimport(monkeypatch):
    maker = _isolated_db(monkeypatch)
    with maker() as db:
        db.add_all([
            _review("msg-sep", "Date Wise 29-09-2026.xls", sample_datewise(), date(2026,9,29)),
            _review("msg-26", "Date Wise 26-10-2026.xls", sample_datewise(), date(2026,10,26)),
        ])
        db.commit()
    result = mail.recheck_archived_despatch(force=True)
    assert result["processedMessages"] == 0
    assert result["tripsInserted"] == 0
    assert result["remainingFiles"] == 0
    with maker() as db:
        attachments = list(db.scalars(select(mail.DespatchMailAttachment)))
        assert all(item.status == "REVIEW_REQUIRED" for item in attachments)
        assert list(db.scalars(select(router.DespatchTrip))) == []



def test_review_api_filters_already_imported_and_limits_results(monkeypatch):
    maker = _isolated_db(monkeypatch)
    with maker() as db:
        for idx in range(20):
            x = _review("msg" + str(idx), "source-"+str(idx)+".xls", b"test", date(2026,10,27))
            if idx % 2 == 0:
                x.status = "IMPORTED"
            db.add(x)
        db.commit()
        monkeypatch.setattr(router, "_user", lambda *args, **kwargs: None)
        result = router.mail_attachments(object(), db)
        assert len(result) == 10
        assert all(x["status"] == "REVIEW_REQUIRED" for x in result)


def test_frontend_only_exceptions_and_single_click_reconcile():
    js = (Path(__file__).parents[1] / "app" / "static" / "tiom_despatch.js").read_text("utf-8")
    assert "New Despatch exceptions · 27 Oct onward" in js
    assert "tiomDDReconcileArchives" in js
    assert "mail-review-reconcile" in js
    assert "Original Date-wise / Transporter-wise XLS summary files" not in js
