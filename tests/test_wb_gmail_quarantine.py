"""Rejected WB Gmail files must survive Render restarts and stay private."""
from datetime import datetime, timezone
from io import BytesIO
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.services.wb_quarantine import WbGmailQuarantine
from app.services.wb_mapping import find_wb_sheet


def test_original_rejected_excel_can_be_stored_and_retrieved_without_changes():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    original = b"PK\\x03\\x04sample workbook bytes"
    with Session(engine) as db:
        record = WbGmailQuarantine(
            file_hash="a"*64,
            gmail_message_id="message-1",
            sender="site@example.org",
            file_name="unrecognized WB.xlsx",
            reason="Unrecognized header",
            file_size=len(original),
            file_data=original,
            received_at=datetime.now(timezone.utc),
        )
        db.add(record)
        db.commit()
        again = db.get(WbGmailQuarantine, "a"*64)
        assert again.file_data == original
        assert again.file_size == len(original)
    engine.dispose()


def test_unknown_layout_gives_sheet_diagnostics_but_never_guesses_trip_columns():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    wb = Workbook()
    ws = wb.active
    ws.title = "SURPRISE REVIEW"
    ws.append(["Vehicle Type", "Total Trip", "Total MT"])
    with Session(engine) as db:
        try:
            find_wb_sheet(wb, db)
            assert False, "Unsafe summary sheet was accepted as WB transaction data"
        except ValueError as exc:
            assert "SURPRISE REVIEW" in str(exc)
            assert "Vehicle Type" in str(exc)
            assert "No WB rows were imported" in str(exc)
    engine.dispose()


def test_wb_error_api_requires_signed_in_user():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "app/routers/webapp.py").read_text("utf-8")
    for endpoint in ("'/wb-gmail-errors'", "'/wb-gmail-errors/{file_hash}'"):
        assert endpoint in source
    block = source[source.index("@router.get('/wb-gmail-errors')"):
                   source.index("def lock(db):")]
    assert block.count("get_user(db, request)") >= 2
    assert block.count("require(user, 'WB')") >= 2
