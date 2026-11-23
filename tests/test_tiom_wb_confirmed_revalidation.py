"""Source-matched correction of stale A-shift WB review rows (no reimport)."""
from datetime import date, datetime, time
from decimal import Decimal
from hashlib import sha256
from io import BytesIO

import pytest
import app.auth  # register user FK target for isolated Base.metadata.create_all
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ShiftMaster, WbImportBatch, WbMovement, AuditLog
from app.services.time_context import TZ
from app.services.tiom_wb_confirmed_revalidation import _confirm_source_and_revalidate


def example_source():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append([
        "Movement No", "Movement Date", "Shift Code", "Vehicle Number",
        "Tare Weight", "Gross Weight", "Net Weight", "GW Created Time",
        "Source Location Id", "Destination Location",
    ])
    sheet.append(["WB001", datetime(2026,11,22), "A", "DT-01",
                  21000, 61000, 40000, time(13,20,3), "SRC", "DST"])
    sheet.append(["WB002", datetime(2026,11,22), "A", "DT-02",
                  21000, 60000, 39000, time(12,22,18), "SRC", "DST"])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def make_db(data):
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db=Session(engine)
    db.add(ShiftMaster(shift="A",start_time=time(6),end_time=time(14),scheduled_hours=8,active=True))
    batch=WbImportBatch(
        batch_id="batch-a", operating_date=date(2026,11,22),shift="A",
        file_name="22.11.2026 A-SHIFT.XLSX", file_hash=sha256(data).hexdigest(),
        status="CONFIRMED",valid_rows=1,review_rows=1,
        confirmed_at=datetime(2026,11,22,14,tzinfo=TZ),
    )
    db.add(batch)
    for no,vehicle,net,time_stamp,status,reason,rno in [
        ("WB001","DT-01",40000,datetime(2026,11,22,6,tzinfo=TZ),
         "REVIEW","Invalid or out-of-shift GW Created Time",2),
        ("WB002","DT-02",39000,datetime(2026,11,22,12,22,18,tzinfo=TZ),
         "VALID",None,3),
    ]:
        db.add(WbMovement(
            movement_key=f"batch-a:{no}:{rno}",batch_id="batch-a",
            operating_date=date(2026,11,22),shift="A",movement_no=no,
            vehicle_raw=vehicle,material_code="ROM",material_name="ROM",
            source_raw="SRC",destination_raw="DST",tare_kg=Decimal(21000),
            gross_kg=Decimal(21000+net),net_kg=Decimal(net),
            weigh_at=time_stamp,row_status=status,issue=reason,
        ))
    db.commit()
    return engine,db,batch


def test_confirmed_review_corrected_using_exact_original(monkeypatch):
    data=example_source()
    engine,db,batch=make_db(data)
    calls=[]
    monkeypatch.setattr(
        "app.services.tiom_wb_confirmed_revalidation.canonicalize_wb_rows",
        lambda session, rows: calls.extend(rows) or {},
    )
    try:
        result=_confirm_source_and_revalidate(db,batch,data)
        assert result["revalidated"]==1
        assert result["valid"]==2 and result["review"]==0
        movement=db.get(WbMovement,"batch-a:WB001:2")
        assert movement.row_status=="VALID"
        assert movement.weigh_at.astimezone(TZ).time()==time(13,20,3)
        assert movement.issue is None
        assert len(calls)==1
        assert db.query(WbMovement).count()==2
        assert db.query(WbImportBatch).count()==1
        assert db.query(AuditLog).filter(AuditLog.action=="TIOM_WB_SOURCE_TIME_REVALIDATED").count()==1
        again=_confirm_source_and_revalidate(db,batch,data)
        assert again["revalidated"]==0
        assert db.query(AuditLog).filter(AuditLog.action=="TIOM_WB_SOURCE_TIME_REVALIDATED").count()==1
    finally:
        db.close();engine.dispose()


def test_confirmed_review_requires_matching_file_hash(monkeypatch):
    data=example_source()
    engine,db,batch=make_db(data)
    try:
        with pytest.raises(ValueError,match="SHA256"):
            _confirm_source_and_revalidate(db,batch,data+b"x")
        assert batch.review_rows==1
        assert db.get(WbMovement,"batch-a:WB001:2").row_status=="REVIEW"
    finally:
        db.close();engine.dispose()


def test_reviewer_does_not_promote_other_errors(monkeypatch):
    data=example_source()
    engine,db,batch=make_db(data)
    monkeypatch.setattr(
        "app.services.tiom_wb_confirmed_revalidation.canonicalize_wb_rows",
        lambda session, rows: {},
    )
    try:
        movement=db.get(WbMovement,"batch-a:WB001:2")
        movement.issue="Invalid or out-of-shift GW Created Time; Invalid tare/gross/net weight"
        db.commit()
        result=_confirm_source_and_revalidate(db,batch,data)
        assert result["revalidated"]==0
        assert movement.row_status=="REVIEW"
    finally:
        db.close();engine.dispose()
