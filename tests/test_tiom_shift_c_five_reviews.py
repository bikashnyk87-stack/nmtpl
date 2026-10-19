"""TIOM 5 AM, 1 PM, 9 PM operational shifts and 11-Oct five WB reviews."""
from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AuditLog, ShiftMaster, WbImportBatch, WbMovement
from app.site_models import Site, SiteShift
from app.services.tiom_shift_alignment import (
    TIMES, EXCEPTIONS, DAY, align_tiom_shifts, resolve_oct11_five_wb_reviews,
)
from app.services.wb_mapping import (clock_in_shift,expected_movement_date,
    validate_wb_operational_metadata)


def test_tiom_shift_master_aligned_without_changing_socp_or_kocp():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Site(site_id="TIOM",site_name="TIOM",short_name="TIOM",timezone="Asia/Kolkata",active=True),
            Site(site_id="SOCP",site_name="SOCP",short_name="SOCP",timezone="Asia/Kolkata",active=True),
            Site(site_id="KOCP",site_name="KOCP",short_name="KOCP",timezone="Asia/Kolkata",active=True),
            SiteShift(site_id="SOCP",shift="C",start_time=time(22),end_time=time(6),
                      shift_name="Shift C",scheduled_hours=8,sequence_no=3,active=True),
            SiteShift(site_id="KOCP",shift="C",start_time=time(21),end_time=time(5),
                      shift_name="Shift C",scheduled_hours=8,sequence_no=3,active=True),
        ])
        for shift,minutes in (("A",(6,14)),("B",(14,22)),("C",(22,6))):
            db.add(ShiftMaster(shift=shift,start_time=time(minutes[0]),end_time=time(minutes[1]),
                               scheduled_hours=8,active=True))
        db.flush()
        assert align_tiom_shifts(db)["aligned"]==["A","B","C"]
        assert align_tiom_shifts(db)["aligned"]==[]
        for sh,(start,end,_) in TIMES.items():
            assert db.get(ShiftMaster,sh).start_time==start
            assert db.get(ShiftMaster,sh).end_time==end
            assert db.get(SiteShift,{"site_id":"TIOM","shift":sh}).start_time==start
        assert db.get(SiteShift,{"site_id":"SOCP","shift":"C"}).start_time==time(22)
        assert db.get(SiteShift,{"site_id":"KOCP","shift":"C"}).start_time==time(21)
    engine.dispose()


def test_all_five_c_shift_times_and_midnight_date_convention():
    c=SimpleNamespace(start_time=time(21),end_time=time(5))
    b=SimpleNamespace(start_time=time(13),end_time=time(21))
    clocks=[time(21,33,33),time(21,37,45),time(21,51,44),time(21,53,2),time(0,0,27)]
    assert all(clock_in_shift(c,x) for x in clocks)
    assert all(not clock_in_shift(b,x) for x in clocks)
    for x in clocks[:4]:
        issues,notes=validate_wb_operational_metadata(DAY,"C","B",DAY,x,c)
        assert issues==[]
        assert any("SAP Shift B" in n for n in notes)
    midnight=clocks[-1]
    assert expected_movement_date(DAY,midnight,c)==date(2026,10,12)
    problems,notes=validate_wb_operational_metadata(DAY,"C","C",DAY,midnight,c)
    assert problems==[]
    assert any("operational date" in n for n in notes)
    problems,_=validate_wb_operational_metadata(DAY,"C","C",date(2026,10,10),midnight,c)
    assert problems
    assert all(datetime.fromisoformat(EXCEPTIONS[k][1]).time() in clocks for k in EXCEPTIONS)


def seed_wb(db):
    db.add(WbImportBatch(batch_id="confirmed-C",operating_date=DAY,shift="C",
        file_name="WB",file_hash="abc",status="CONFIRMED",valid_rows=10,review_rows=5,
        confirmed_at=datetime(2026,10,12,6)))
    for no,(vehicle,physical,mt,material) in EXCEPTIONS.items():
        issue=("Shift B != selected C" if no!="20264014112808" else
            "Movement Date 2026-10-11 != expected calendar date 2026-10-12 for operating date 2026-10-11 / Shift C")
        db.add(WbMovement(movement_key="confirmed-C:"+no,batch_id="confirmed-C",
            operating_date=DAY,shift="C",movement_no=no,vehicle_raw=vehicle,vehicle_id=vehicle,
            material_code="X",material_name=material,source_raw="SRC",destination_raw="DST",
            tare_kg=Decimal("12000"),gross_kg=Decimal("12000")+mt*1000,net_kg=mt*1000,
            weigh_at=datetime(2026,10,11,22,0),row_status="REVIEW",issue=issue))
    db.flush()


def test_all_five_review_movements_corrected_once_with_original_evidence():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_wb(db)
        result=resolve_oct11_five_wb_reviews(db)
        assert result["corrected"]==5,result
        assert result["skipped"]=={}
        batch=db.get(WbImportBatch,"confirmed-C")
        assert batch.valid_rows==15 and batch.review_rows==0
        for no,(_,physical,mt,_) in EXCEPTIONS.items():
            w=db.get(WbMovement,"confirmed-C:"+no)
            assert w.row_status=="VALID"
            assert w.weigh_at.replace(tzinfo=None)==datetime.fromisoformat(physical)
            assert w.net_kg/Decimal(1000)==mt
            assert w.issue.startswith("VERIFIED_TIOM_SHIFT_C_21_TO_05:")
        logs=list(db.scalars(select(AuditLog).where(AuditLog.action=="TIOM_WB_REVIEW_SHIFT_C_VERIFIED")))
        assert len(logs)==5
        again=resolve_oct11_five_wb_reviews(db)
        assert again["corrected"]==0 and again["alreadyValid"]==5
        assert len(list(db.scalars(select(AuditLog).where(
            AuditLog.action=="TIOM_WB_REVIEW_SHIFT_C_VERIFIED"))))==5
    engine.dispose()


def test_duplicate_wb_movement_prevents_review_promotion():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_wb(db)
        no="20264014112738"
        db.add(WbImportBatch(batch_id="active-B",operating_date=DAY,shift="B",
            file_name="other",file_hash="xyz",status="CONFIRMED",valid_rows=1,
            review_rows=0,confirmed_at=datetime(2026,10,11,23)))
        db.add(WbMovement(movement_key="active-B:"+no,batch_id="active-B",
            operating_date=DAY,shift="B",movement_no=no,vehicle_raw="DT-06",
            material_name="ROM Thakurani",net_kg=Decimal("51520"),tare_kg=Decimal("1"),
            gross_kg=Decimal("51521"),row_status="VALID"))
        db.flush()
        result=resolve_oct11_five_wb_reviews(db)
        assert result["corrected"]==4
        assert result["skipped"][no]=="DUPLICATE_ACTIVE_CONFIRMED_WB"
        assert db.get(WbMovement,"confirmed-C:"+no).row_status=="REVIEW"
    engine.dispose()
