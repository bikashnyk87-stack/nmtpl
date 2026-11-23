"""TIOM effective 1-Oct 06/14/22 shifts; former C reviews require audit."""
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
        for shift,minutes in (("A",(5,13)),("B",(13,21)),("C",(21,5))):
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


def test_october_11_physical_clock_uses_new_shift_boundaries():
    from app.services.tiom_shift_schedule import context_at, definition_for_day
    from app.services.time_context import TZ
    new_b=SimpleNamespace(shift="B",start_time=time(14),end_time=time(22),
                          active=True,scheduled_hours=8)
    new_c=SimpleNamespace(shift="C",start_time=time(22),end_time=time(6),
                          active=True,scheduled_hours=8)
    b=definition_for_day(DAY,new_b)
    c=definition_for_day(DAY,new_c)
    for _,(vehicle,physical,mt,material) in list(EXCEPTIONS.items())[:4]:
        assert clock_in_shift(b,datetime.fromisoformat(physical).time())
        assert not clock_in_shift(c,datetime.fromisoformat(physical).time())
        assert context_at(datetime.fromisoformat(physical).replace(tzinfo=TZ))==(DAY,"B")
    midnight=datetime(2026,10,12,0,0,27,tzinfo=TZ)
    assert context_at(midnight)==(DAY,"C")
    assert expected_movement_date(DAY,midnight.time(),c)==date(2026,10,12)
    assert definition_for_day(date(2026,9,30),new_c).start_time==time(21)



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


def test_legacy_oct11_reviews_are_not_auto_promoted_on_restart():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_wb(db)
        original={
            no:(db.get(WbMovement,"confirmed-C:"+no).row_status,
                db.get(WbMovement,"confirmed-C:"+no).weigh_at)
            for no in EXCEPTIONS
        }
        result=resolve_oct11_five_wb_reviews(db)
        assert result["corrected"]==0
        assert "policy" in result["skipped"]
        batch=db.get(WbImportBatch,"confirmed-C")
        assert batch.valid_rows==10 and batch.review_rows==5
        for no in EXCEPTIONS:
            wb=db.get(WbMovement,"confirmed-C:"+no)
            assert (wb.row_status,wb.weigh_at)==original[no]
        assert not list(db.scalars(select(AuditLog).where(
            AuditLog.action=="TIOM_WB_REVIEW_SHIFT_C_VERIFIED")))
    engine.dispose()



def test_existing_duplicate_does_not_trigger_silent_reclassification():
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
            gross_kg=Decimal("51521"),weigh_at=datetime(2026,10,11,20,45),row_status="VALID"))
        db.flush()
        result=resolve_oct11_five_wb_reviews(db)
        assert result["corrected"]==0
        assert db.get(WbMovement,"confirmed-C:"+no).row_status=="REVIEW"
        assert db.get(WbMovement,"active-B:"+no).row_status=="VALID"
    engine.dispose()
