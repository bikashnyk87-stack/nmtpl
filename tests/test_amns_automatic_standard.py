"""Standard AMNS report processing: no manual date/permit/grade/MT entry.

Synthetic OCR tokens exercise the October 27 control report. No user image,
Gmail token or private files are checked into the repository.
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base
from app.routers import tiom_despatch as router
from app.services.tiom_despatch_amns import (
    read_report, plan_reconciliation, apply_reconciliation, AMNSException
)


def _token(text, y, x=100):
    return {"text":text, "y":y,"x":x,"score":0.99}


def _source_report():
    return [
        _token("DATE WISE DISPATCH REPORT ON DATED - 27.10.2026",20),
        _token("1 L102604670 AMNS DABUNA SCREENED FINES 60.79% 13878.090 85 2559.290 11286.950",100),
        _token("2 L102604460 AMNS DABUNA SCREENED FINES 60.79% 15909.770 421 12981.390 0.070",130),
        _token("3 L102602644 DNA MINERALS TUIDUNGRI (SARAIKELA) 5X18 60.50% 4000.000 21 669.070 482.540",160),
        _token("4 L102603256 SNN MINERALS TUIDUNGRI (SARAIKELA) 5X18 60.50% 1015.030 4 128.620 116.820",190),
        _token("TOTAL 531 16338.370",220),
        _token("Note - 01 No. T.P Cancelled Permit/Pass -No- L102604670/80(AM/NS-Dabuna) Screened Fines -31.850 M.T",420),
    ]


def _setup():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},
                         poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[
        router.DespatchTrip.__table__,
        router.DespatchDocument.__table__,
        router.DespatchPermitDay.__table__,
        router.DespatchAudit.__table__,
    ])
    return engine


def _trip(epass,permit,mt,day=date(2026,10,27),buyer="",dest="",grade=""):
    return router.DespatchTrip(
        epass_no=epass,report_date=day,permit_no=permit,
        permit_qty=Decimal("50000.000"),buyer=buyer,destination=dest,
        material_grade=grade,consignee="",vehicle_no="OD09Z1234",transporter="TRANSPORTER",
        tare_mt=Decimal("15.000"),gross_mt=Decimal(str(mt))+Decimal("15.000"),
        net_mt=Decimal(str(mt)),status="ACTIVE",source="UNIT TEST",
    )


def _populate_day(db):
    before=date(2026,10,26)
    db.add_all([
        _trip("OLD-DNA","L102602644","25",before,
              "DNA MINERALS PVT LTD","Chandil","5-18mm(60-62)"),
        _trip("OLD-SNN","L102603256","25",before,
              "S N N MINERALS PRIVATE LIMITED.","Chandil","5-18mm(60-62)"),
    ])
    valid_epasses=[i for i in range(1,87) if i!=80]
    assert len(valid_epasses)==85
    for i,epass_no in enumerate(valid_epasses):
        db.add(_trip(f"L102604670/{epass_no}","L102604670",
                     "39.290" if i==84 else "30.000"))
    # /80 is the precisely identified cancelled E-Pass; replace its original
    # weight with 31.850 and compensate another active E-Pass to keep the
    # screenshot source amount of 2591.140.
    db.add(_trip("L102604670/80","L102604670","31.850"))
    # Excluding /80 from the valid 85 must total 2559.290.
    for i in range(421):
        db.add(_trip(f"L102604460/{i+1}","L102604460",
                     "45.390" if i==420 else "30.800"))
    for i in range(21):
        db.add(_trip(f"L102602644/{i+1}","L102602644",
                     "32.070" if i==20 else "31.850"))
    for i in range(4):
        db.add(_trip(f"L102603256/{i+1}","L102603256",
                     "32.620" if i==3 else "32.000"))
    image = router.DespatchDocument(
        id="OCR-IMAGE", report_date=date(2026,10,27),
        filename="amns-27oct.jpeg",media_type="image/jpeg",
        sha256="f"*64,image_data=b"TEST",review_status="NEEDS_REVIEW")
    db.add(image)
    db.commit()
    return image


def test_report_parsed_from_image_tokens_with_cancellation():
    report=read_report(_source_report(),1079,461)
    assert report["report_date"]==date(2026,10,27)
    assert report["reported_trips"]==531
    assert report["reported_mt"]==Decimal("16338.370")
    assert report["cancellations"]==[
        {"epass_no":"L102604670/80","net_mt":Decimal("31.850")}
    ]
    rows={r["permit_no"]:r for r in report["permits"]}
    assert len(rows)==4
    assert rows["L102604670"]["trips"]==85
    assert rows["L102604670"]["buyer"]=="Self"
    assert rows["L102604670"]["destination"]=="Dabuna"
    assert rows["L102604670"]["material_grade"]=="S.Fines(60-62)"
    assert rows["L102602644"]["material_grade"]=="5-18mm(60-62)"
    assert rows["L102602644"]["destination"] is None


def test_cancel_exact_epass_and_reconcile_image_without_changing_oct26():
    engine=_setup()
    with Session(engine) as db:
        doc=_populate_day(db)
        before=list(db.scalars(select(router.DespatchTrip).where(
            router.DespatchTrip.report_date==date(2026,10,27))))
        assert len(before)==532
        assert sum((Decimal(str(x.net_mt)) for x in before),Decimal(0))==Decimal("16370.220")
        report=read_report(_source_report(),1079,461)
        preview=plan_reconciliation(db,report)
        assert preview["verifiedTrips"]==531
        assert preview["verifiedMt"]==Decimal("16338.370")
        result=apply_reconciliation(db,doc,report)
        assert result["verifiedTrips"]==531
        assert result["verifiedMt"]==16338.37
        assert result["cancelledEPasses"]==["L102604670/80"]
        assert db.get(router.DespatchTrip,"L102604670/80").status=="CANCELLED"
        assert db.get(router.DespatchDocument,"OCR-IMAGE").review_status=="VERIFIED"
        active=list(db.scalars(select(router.DespatchTrip).where(
            router.DespatchTrip.report_date==date(2026,10,27),
            router.DespatchTrip.status=="ACTIVE")))
        assert len(active)==531
        assert sum((Decimal(str(x.net_mt)) for x in active),Decimal(0))==Decimal("16338.370")
        assert db.get(router.DespatchTrip,"L102604670/1").buyer=="Self"
        assert db.get(router.DespatchTrip,"L102604670/1").material_grade=="S.Fines(60-62)"
        assert db.get(router.DespatchTrip,"OLD-DNA").buyer=="DNA MINERALS PVT LTD"
        assert db.get(router.DespatchTrip,"OLD-DNA").report_date==date(2026,10,26)
        # Repeat processing must be idempotent.
        assert apply_reconciliation(db,doc,report)["verifiedTrips"]==531


def test_cancellation_weight_mismatch_never_changes_database():
    engine=_setup()
    with Session(engine) as db:
        doc=_populate_day(db)
        report=read_report(_source_report(),1079,461)
        report["cancellations"][0]["net_mt"]=Decimal("32.000")
        with pytest.raises(AMNSException,match="Cancellation weight"):
            apply_reconciliation(db,doc,report)
        db.rollback()
        assert db.get(router.DespatchDocument,"OCR-IMAGE").review_status=="NEEDS_REVIEW"
        assert db.get(router.DespatchTrip,"L102604670/80").status=="ACTIVE"


def test_missing_cancellation_blocks_report_dont_invent_531_trips():
    engine=_setup()
    with Session(engine) as db:
        _populate_day(db)
        report=read_report(_source_report(),1079,461)
        report["cancellations"]=[]
        with pytest.raises(AMNSException,match="Permit"):
            plan_reconciliation(db,report)
        assert db.get(router.DespatchTrip,"L102604670/80").status=="ACTIVE"


def test_unreadable_row_and_short_or_ambiguous_grade_fail_closed():
    bad=_source_report()
    bad[1]=_token("L102604670 AMNS DABUNA SCREENED FINES 60.79% 13878.090 85 NO_VALUE 11286.950",100)
    with pytest.raises(AMNSException,match="Unreadable AMNS table"):
        read_report(bad,1079,461)
    from app.services.tiom_despatch_amns import grade_bucket
    with pytest.raises(AMNSException):
        grade_bucket("69.20","SCREENED FINES")


def test_mail_worker_has_automatic_amns_integration_and_retains_older_ledger():
    from pathlib import Path
    src=(Path(__file__).parents[1]/"app/services/tiom_despatch_mail.py").read_text("utf8")
    assert "auto_process_pending_images" in src
    from app.services.tiom_despatch_amns import OPEN_DAY
    assert OPEN_DAY==date(2026,10,27)
