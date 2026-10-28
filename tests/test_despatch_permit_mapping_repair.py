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
                                     permit_no="NEW",category_index=3,
                                     document_id="NONEXISTENT",expected_trips=86)
        with pytest.raises(ValueError,match="trip count"):
            apply_confirmed_category(db,actor="ADMIN",report_date=today,
                                     permit_no="NEW",category_index=3,
                                     document_id="IMAGE-27",expected_trips=85)
        result=apply_confirmed_category(db,actor="ADMIN",report_date=today,
                                       permit_no="NEW",category_index=3,
                                       document_id="IMAGE-27",expected_trips=86)
        assert result["tripsChecked"]==86
        assert result["changedFields"]==3*86
        assert mapping_status(db,today)["unmappedTrips"]==0
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
                permit_no="NEW",category_index=3,document_id="IMG",expected_trips=1)
        assert db.get(router.DespatchTrip,"NEW/1").destination==""


def test_ui_offers_single_permit_confirmation_and_bulk_safe_repair():
    from pathlib import Path
    src=(Path(__file__).parents[1]/"app"/"static"/"tiom_despatch.js").read_text("utf-8")
    for phrase in ("mapping-status","mapping-reconcile","mapping-confirm",
                   "tiomDDRepairCategories","tiomDDConfirmCategory",
                   "Confirm one permit","Source mapping"):
        assert phrase in src
