"""Preserve 1–26 Oct Despatch and repair 27 Oct classifications from exact permits."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.routers import tiom_despatch as router
from app.services.tiom_despatch_mapping import (
    apply_confirmed_category, mapping_status, reconcile_known_permits,
)


def _setup():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine, tables=[
        router.DespatchTrip.__table__,router.DespatchAudit.__table__,
        router.DespatchDocument.__table__,
    ])
    return engine


def _trip(epass, permit, day, buyer="", dest="", mat="",consignee=""):
    return router.DespatchTrip(
        epass_no=epass,permit_no=permit,report_date=day,permit_qty=Decimal("4000"),
        buyer=buyer,destination=dest,material_grade=mat,
        consignee=consignee,vehicle_no="OD09Z1",transporter="MST",
        tare_mt=Decimal("15"),gross_mt=Decimal("45"),net_mt=Decimal("30"),
        status="ACTIVE",source="TEST",
    )


def test_confident_old_permit_fill_leaves_new_permit_unmapped():
    engine=_setup()
    old=date(2026,10,26); new=date(2026,10,27)
    with Session(engine) as db:
        for permit,buyer,destination,grade in [
            ("L102602644","DNA MINERALS PVT LTD","Chandil","5-18mm(60-62)"),
            ("L102603256","S N N MINERALS PRIVATE LIMITED.","Chandil","5-18mm(60-62)"),
            ("L102604460","Self","Dabuna","S.Fines(60-62)"),
        ]:
            db.add(_trip(permit+"/H",permit,old,buyer,destination,grade,"same-consignee"))
        for permit,count in [
            ("L102602644",21),("L102603256",4),
            ("L102604460",421),("L102604670",86),
        ]:
            for i in range(count):
                db.add(_trip(f"{permit}/{i}",permit,new,consignee="same-consignee"))
        db.commit()
        before=sum(float(t.net_mt) for t in db.scalars(
            select(router.DespatchTrip).where(router.DespatchTrip.report_date==new)))
        result=reconcile_known_permits(db)
        assert result["updatedTrips"]==446
        assert result["updatedPermits"]==3
        status=mapping_status(db,new)
        assert status["totalTrips"]==532
        assert status["unmappedTrips"]==86
        assert len(status["permits"])==1
        assert status["permits"][0]["permit_no"]=="L102604670"
        assert status["permits"][0]["classification"]=="VERIFY_NEW_PERMIT"
        after=sum(float(t.net_mt) for t in db.scalars(
            select(router.DespatchTrip).where(router.DespatchTrip.report_date==new)))
        assert before==after==532*30.0
        hist=db.scalar(select(router.DespatchTrip).where(
            router.DespatchTrip.epass_no=="L102604460/H"))
        assert hist.buyer=="Self" and hist.report_date==old
        assert reconcile_known_permits(db)["updatedTrips"]==0
        assert len(list(db.scalars(select(router.DespatchAudit))))==3


def test_conflicting_historical_grades_cannot_autofill():
    engine=_setup()
    with Session(engine) as db:
        db.add_all([
            _trip("X/1","X",date(2026,10,20),"Self","Dabuna","S.Fines(60-62)"),
            _trip("X/2","X",date(2026,10,22),"Self","Dabuna","S.Fines(62-65)"),
            _trip("X/3","X",date(2026,10,27)),
        ])
        db.commit()
        assert reconcile_known_permits(db)["updatedTrips"]==0
        assert db.get(router.DespatchTrip,"X/3").material_grade==""


def test_new_permit_requires_matching_amns_image_and_explicit_choice():
    engine=_setup()
    with Session(engine) as db:
        today=date(2026,10,27)
        for i in range(86):
            db.add(_trip(f"NEW/{i}","NEW",today))
        db.add(router.DespatchDocument(
            id="IMAGE-27",report_date=today,filename="AMNS 27-Oct.jpeg",
            media_type="image/jpeg",sha256="1234567890"*6+"1234",
            image_data=b"TEST",review_status="NEEDS_REVIEW",
        ))
        db.commit()
        with pytest.raises(ValueError,match="AMNS image"):
            apply_confirmed_category(db,actor="ADMIN",report_date=today,
                                     permit_no="NEW",category_index=6,
                                     document_id="NONEXISTENT",expected_trips=86)
        with pytest.raises(ValueError,match="trip count"):
            apply_confirmed_category(db,actor="ADMIN",report_date=today,
                                     permit_no="NEW",category_index=6,
                                     document_id="IMAGE-27",expected_trips=85)
        result=apply_confirmed_category(db,actor="ADMIN",report_date=today,
                                       permit_no="NEW",category_index=6,
                                       document_id="IMAGE-27",expected_trips=86)
        assert result["tripsChecked"]==86
        assert result["changedFields"]==3*86
        status=mapping_status(db,today)
        assert status["unmappedTrips"]==0
        assert all(x["index"]!=3 for x in status["categories"])
        assert sum(float(t.net_mt) for t in db.scalars(select(router.DespatchTrip)))==86*30


def test_nonempty_conflicting_source_category_blocks_bulk_change():
    engine=_setup()
    with Session(engine) as db:
        db.add(_trip("NEW/1","NEW",date(2026,10,27),"DNA MINERALS PVT LTD"))
        db.add(router.DespatchDocument(id="IMG",report_date=date(2026,10,27),
                    filename="source.jpeg",media_type="image/jpeg",
                    sha256="a"*64,image_data=b"JPEG"))
        db.commit()
        with pytest.raises(ValueError,match="conflicts"):
            apply_confirmed_category(db,actor="ADMIN",report_date=date(2026,10,27),
                permit_no="NEW",category_index=6,document_id="IMG",expected_trips=1)
        assert db.get(router.DespatchTrip,"NEW/1").destination==""


def test_ui_offers_single_permit_confirmation_and_bulk_safe_repair():
    from pathlib import Path
    src=(Path(__file__).parents[1]/"app"/"static"/"tiom_despatch.js").read_text("utf-8")
    for phrase in ("mapping-status","mapping-reconcile","mapping-confirm",
                   "tiomDDRepairCategories","tiomDDConfirmCategory",
                   "Confirm permit classification","Source mapping"):
        assert phrase in src


def test_earlier_image_visible_and_exact_continuing_permit_maps_multiple_dates_safely():
    from app.services.tiom_despatch_client_layout import DESTINATION_BUCKETS
    engine = _setup()
    source_date = date(2026, 10, 30)
    oct31 = date(2026, 10, 31)
    nov1 = date(2026, 11, 1)
    nov2 = date(2026, 11, 2)
    ph_bucket = next(i for i, (buyer, dest, mat) in enumerate(DESTINATION_BUCKETS)
                     if buyer == "PH ASSOCIATES PRIVATE LIMITED"
                     and dest == "Kuarmunda(SNG)"
                     and mat == "5-18mm(60-62)")
    with Session(engine) as db:
        db.add(router.DespatchDocument(
            id="AMNS-30", report_date=source_date, filename="30.10.26.jpeg",
            media_type="image/jpeg", sha256="f"*64,
            image_data=b"ARCHIVED-IMAGE", review_status="EVIDENCE_ONLY"))
        db.add(router.DespatchDocument(
            id="FUTURE", report_date=date(2026, 11, 3), filename="future.jpeg",
            media_type="image/jpeg", sha256="e"*64, image_data=b"FUTURE"))
        db.add(_trip("OLD/1","L102601592",date(2026,10,26),
                     buyer="LEGACY", dest="Dabuna", mat="S.Fines(60-62)"))
        for day,count in ((oct31,7),(nov1,3),(nov2,1)):
            for i in range(count):
                row = _trip(f"{day}/{i}","L102601592",day,
                            consignee="081813771711/PH ASSOCIATES PRIVATE LIMITED")
                row.net_mt = Decimal("24.55") if day == nov2 else Decimal("30.5")
                db.add(row)
        db.add(_trip("UNRELATED", "L102604965", nov2,
                     consignee="A DIFFERENT COMPANY"))
        db.commit()
        before = {(x.epass_no, x.report_date, x.status, x.net_mt)
                  for x in db.scalars(select(router.DespatchTrip))}
        preview = mapping_status(db, nov2)
        doc = next(x for x in preview["images"] if x["id"]=="AMNS-30")
        assert doc == {"id":"AMNS-30", "name":"30.10.26.jpeg",
                       "reportDate":"2026-10-30", "status":"EVIDENCE_ONLY",
                       "earlierEvidence":True}
        assert all(x["id"]!="FUTURE" for x in preview["images"])
        permit = next(x for x in preview["permits"] if x["permit_no"] == "L102601592")
        assert permit["relatedUnclassifiedTrips"] == 11
        assert permit["relatedDates"] == ["2026-10-31","2026-11-01","2026-11-02"]
        with pytest.raises(ValueError, match="on or before"):
            apply_confirmed_category(db,actor="ADMIN",report_date=nov2,
                permit_no="L102601592",category_index=ph_bucket,
                document_id="FUTURE",expected_trips=1)
        confirmed = apply_confirmed_category(db,actor="ADMIN",
            report_date=nov2, permit_no="L102601592",
            category_index=ph_bucket,document_id="AMNS-30",expected_trips=1)
        assert confirmed["tripsChecked"] == 1  # selected-day trips only
        assert confirmed["changedTripCount"] == 11
        assert confirmed["changedFields"] == 33
        assert confirmed["changedDates"] == ["2026-10-31","2026-11-01","2026-11-02"]
        rows=list(db.scalars(select(router.DespatchTrip)))
        assert before == {(x.epass_no,x.report_date,x.status,x.net_mt) for x in rows}
        active=[x for x in rows if x.permit_no=="L102601592" and x.report_date>=oct31]
        assert len(active)==11
        assert all(x.buyer=="PH ASSOCIATES PRIVATE LIMITED" and
                   x.destination=="Kuarmunda(SNG)" and
                   x.material_grade=="5-18mm(60-62)" for x in active)
        assert db.get(router.DespatchTrip,"UNRELATED").buyer == ""
        assert db.get(router.DespatchTrip,"OLD/1").buyer == "LEGACY"
        assert mapping_status(db,nov2)["unmappedTrips"] == 1
        assert apply_confirmed_category(db,actor="ADMIN",report_date=nov2,
            permit_no="L102601592",category_index=ph_bucket,
            document_id="AMNS-30",expected_trips=1)["changedTripCount"] == 0


def test_cross_date_conflict_and_inconsistent_consignee_block_all_changes():
    engine = _setup()
    with Session(engine) as db:
        db.add(router.DespatchDocument(id="AMNS-30",report_date=date(2026,10,30),
            filename="30.10.26.jpeg",media_type="image/jpeg",
            sha256="f"*64,image_data=b"ARCHIVED"))
        db.add(_trip("31/1","SAME",date(2026,10,31),
            buyer="DNA MINERALS PVT LTD",consignee="same"))
        db.add(_trip("02/1","SAME",date(2026,11,2),
            consignee="same"))
        db.commit()
        with pytest.raises(ValueError, match="conflicts"):
            apply_confirmed_category(db,actor="ADMIN",report_date=date(2026,11,2),
                permit_no="SAME",category_index=31,
                document_id="AMNS-30",expected_trips=1)
        assert db.get(router.DespatchTrip,"02/1").buyer == ""
        db.get(router.DespatchTrip,"31/1").buyer=""
        db.get(router.DespatchTrip,"31/1").consignee="party-one"
        db.get(router.DespatchTrip,"02/1").consignee="party-two"
        db.commit()
        with pytest.raises(ValueError, match="inconsistent consignee"):
            apply_confirmed_category(db,actor="ADMIN",report_date=date(2026,11,2),
                permit_no="SAME",category_index=31,
                document_id="AMNS-30",expected_trips=1)
        assert db.get(router.DespatchTrip,"02/1").buyer == ""
        single = apply_confirmed_category(db,actor="ADMIN",report_date=date(2026,11,2),
                permit_no="SAME",category_index=31,
                document_id="AMNS-30",expected_trips=1,
                apply_to_related_dates=False)
        assert single["changedTripCount"] == 1
        assert single["changedDates"] == ["2026-11-02"]
        assert db.get(router.DespatchTrip,"31/1").buyer == ""
        assert db.get(router.DespatchTrip,"02/1").buyer == "PH ASSOCIATES PRIVATE LIMITED"


def test_ui_displays_original_image_date_and_manual_verification():
    from pathlib import Path
    ui=(Path(__file__).parents[1]/"app"/"static"/"tiom_despatch.js").read_text("utf-8")
    assert "img.reportDate" in ui
    assert "earlierEvidence" in ui
    assert "tiomDDEvidencePreview" in ui
    assert "View original" in ui
    assert "selected E-Pass date" in ui
    assert "Existing E-Pass dates, weights, trip counts and cancelled rows" in ui
