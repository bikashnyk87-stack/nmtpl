"""KOCP source-backed loader/tipper reporting and MCL entry visibility."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Equipment
from app.site_models import Site, SiteTrip, SiteMaterial, SiteSurveyMeasurement
from app.routers import kocp_shift_register as register
from app.routers import site_ops


def test_loader_tip_trips_and_entered_mcl_qty_visible(monkeypatch):
    db_engine = create_engine("sqlite://", poolclass=StaticPool,
                              connect_args={"check_same_thread":False})
    Base.metadata.create_all(db_engine)
    who = SimpleNamespace(admin=True, login_id="MIS")
    monkeypatch.setattr(register, "get_user", lambda *args: who)
    monkeypatch.setattr(register, "require_site", lambda *args: "KOCP")
    monkeypatch.setattr(site_ops, "get_user", lambda *args: who)
    monkeypatch.setattr(site_ops, "require_site", lambda *args: "KOCP")
    day = date(2026,11,19)
    with Session(db_engine) as db:
        db.add(Site(site_id="KOCP",site_name="KOCP",short_name="KOCP",active=True))
        db.add_all([
            Equipment(machine_id="T1",door_no="V01",type="TIPPER",group="COAL",active=True),
            Equipment(machine_id="L1",door_no="LD01",type="LOADER",group="COAL",active=True),
            Equipment(machine_id="E1",door_no="EX01",type="EXCAVATOR",group="COAL",active=True),
        ])
        db.add(SiteMaterial(site_material_id="COAL",site_id="KOCP",code="COAL",name="Coal",
                            default_unit="MT",active=True))
        for tid,tip,loader,count in [("TEST-L","T1","L1",7),("TEST-E","T1","E1",3)]:
            db.add(SiteTrip(trip_id=tid,site_id="KOCP",operating_date=day,
                shift="A",vehicle_id=tip,loading_equipment_id=loader,
                material_id="COAL",trip_count=count,status="POSTED",
                source_type="SHIFT_COAL_REGISTER",entered_by="MIS"))
        db.add(SiteSurveyMeasurement(measurement_id="MCL-CERT-1",site_id="KOCP",
            period_start=day,period_end=day,material_id="COAL",
            measurement_type="MCL_SURVEY",measured_mt=Decimal("420"),
            measured_cum=Decimal("0"),source_org="MCL",status="DRAFT",entered_by="MIS"))
        db.commit()
        matrix = register.loading_tipper_report(object(),day,day,db)
        assert matrix["count"] == 2
        assert {(row["type"],row["trips"]) for row in matrix["rows"]} == {
            ("LOADER",7),("EXCAVATOR",3)}
        assert {row["tipperId"] for row in matrix["rows"]} == {"T1"}
        report = site_ops.kocp_point_wise_report(object(),day,day,db)
        assert report["pendingOperationalTrips"] == 10
        certified = report["mclCertifiedEntries"][0]
        assert certified["status"] == "DRAFT"
        assert Decimal(certified["certifiedMt"]) == Decimal("420")
        assert report["totals"]["COAL"]["quantity"] == "0"
    db_engine.dispose()
