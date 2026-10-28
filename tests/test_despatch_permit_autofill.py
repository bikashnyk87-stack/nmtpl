"""AMNS permit verification is prefilled from validated E-Pass ledger.

Never fabricate image-only quantities/grade, do not modify source E-Passes,
and distinguish verified images from those still awaiting human comparison.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.routers import tiom_despatch as despatch


def _test_client(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine,tables=[
        despatch.DespatchTrip.__table__, despatch.DespatchDocument.__table__,
        despatch.DespatchPermitDay.__table__, despatch.DespatchAudit.__table__,
    ])
    app=FastAPI()
    app.include_router(despatch.router)
    def get_session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[despatch.get_db]=get_session
    monkeypatch.setattr(despatch,"get_user",lambda db,request: SimpleNamespace(admin=True,login_id="TEST_ADMIN"))
    monkeypatch.setattr(despatch,"require",lambda *args,**kwargs:None)
    monkeypatch.setattr(despatch,"csrf",lambda *args,**kwargs:None)
    return TestClient(app),engine


def _add_trip(db,key,permit,amount=Decimal("32.500"),buyer="DNA MINERALS PVT LTD",destination="Chandil",grade="5-18mm(60-62)",day=date(2026,10,27)):
    db.add(despatch.DespatchTrip(
        epass_no=key,report_date=day,permit_no=permit,
        permit_qty=Decimal("500.000"),buyer=buyer,
        destination=destination,material_grade=grade,
        vehicle_no="OD09Z1234",transporter="R",
        net_mt=amount,gross_mt=amount+Decimal("15"),tare_mt=Decimal("15"),
        status="ACTIVE",source="TEST",
    ))


def _add_image(db,image_id,day=date(2026,10,27)):
    db.add(despatch.DespatchDocument(id=image_id,report_date=day,filename="amns.jpeg",
       media_type="image/jpeg",sha256=image_id.ljust(64,"0"),image_data=b"FAKE-DATA",
       review_status="NEEDS_REVIEW"))


def test_prefills_ledger_permit_details_without_guessing_image_quantities(monkeypatch):
    api,engine=_test_client(monkeypatch)
    with Session(engine) as db:
        _add_image(db,"image-27")
        _add_trip(db,"EP-27-1","PERMIT-1")
        _add_trip(db,"EP-27-2","PERMIT-1",Decimal("31.250"))
        _add_trip(db,"EP-27-3","PERMIT-2",Decimal("40.000"),buyer="",destination="",grade="")
        db.commit()
    response=api.get("/api/tiom/despatch/permit-prefill/image-27")
    assert response.status_code==200,response.text
    payload=response.json()
    assert payload["reportDate"]=="2026-10-27"
    assert payload["totalTrips"]==3
    assert payload["totalMt"]==103.75
    permits={p["permit_no"]:p for p in payload["permits"]}
    p=permits["PERMIT-1"]
    assert p["reported_trips"]==2
    assert p["reported_mt"]==63.75
    assert p["buyer"]=="DNA MINERALS PVT LTD"
    assert p["destination"]=="Chandil"
    assert p["material"]=="5-18mm(60-62)"
    assert p["permit_qty"]==500
    assert p["grade_percent"]==""
    assert p["balance_mt"] is None
    assert permits["PERMIT-2"]["buyer"]==""
    assert any("Buyer not provided" in issue for issue in permits["PERMIT-2"]["issues"])


def test_save_checks_ledger_totals_and_marks_image_verified_without_editing_trips(monkeypatch):
    api,engine=_test_client(monkeypatch)
    with Session(engine) as db:
        _add_image(db,"image-27")
        _add_trip(db,"EP-27-1","PERMIT-1")
        _add_trip(db,"EP-27-2","PERMIT-1",Decimal("31.250"))
        db.commit()
    base={"report_date":"2026-10-27","permit_no":"PERMIT-1","buyer":"DNA MINERALS PVT LTD",
          "destination":"Chandil","material":"5-18mm(60-62)","document_id":"image-27",
          "permit_qty":"500","grade_percent":"60","reported_trips":2,
          "reported_mt":"63.750","balance_mt":None}
    bad={**base,"reported_mt":"1.000"}
    reject=api.post("/api/tiom/despatch/permit-review",json=bad)
    assert reject.status_code==422
    with Session(engine) as db:
        assert db.get(despatch.DespatchDocument,"image-27").review_status=="NEEDS_REVIEW"
    accepted=api.post("/api/tiom/despatch/permit-review",json=base)
    assert accepted.status_code==200,accepted.text
    with Session(engine) as db:
        assert db.get(despatch.DespatchDocument,"image-27").review_status=="VERIFIED"
        permit=db.scalar(select(despatch.DespatchPermitDay))
        assert permit.reported_trips==2
        assert permit.reported_mt==Decimal("63.750")
        assert len(list(db.scalars(select(despatch.DespatchTrip))))==2


def test_wrong_image_date_rejected_and_existing_data_preserved(monkeypatch):
    api,engine=_test_client(monkeypatch)
    with Session(engine) as db:
        _add_image(db,"image-26",date(2026,10,26))
        _add_trip(db,"EP-27-1","PERMIT-1")
        db.commit()
    response=api.post("/api/tiom/despatch/permit-review",json={
        "report_date":"2026-10-27","permit_no":"PERMIT-1","document_id":"image-26",
        "reported_trips":1,"reported_mt":"32.500",
    })
    assert response.status_code==422
    with Session(engine) as db:
        assert db.get(despatch.DespatchDocument,"image-26").review_status=="NEEDS_REVIEW"
        assert len(list(db.scalars(select(despatch.DespatchTrip))))==1


def test_frontend_fetches_original_image_and_prefills_permit_selector():
    from pathlib import Path
    js=(Path(__file__).parents[1]/"app"/"static"/"tiom_despatch.js").read_text(encoding="utf-8")
    assert "permit-prefill/" in js
    assert "tiomDDPickPermit" in js
    assert "No trip records are edited by this form" in js
    assert "Do not guess material grade" in js
    assert "x.review_status==='NEEDS_REVIEW'" in js
