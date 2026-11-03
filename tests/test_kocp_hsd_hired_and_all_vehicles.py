"""Hired KOCP fuel eligibility and untruncated date/shift vehicle report."""
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Equipment
from app.site_models import (
    Site, EquipmentSiteAssignment, SiteShift, SiteHsdTransaction, SiteAuditLog,
)
from app.routers import sites, site_ops

DAY = date(2026, 11, 1)
ROOT = Path(__file__).resolve().parents[1]


def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP", site_name="KOCP", short_name="KOCP", active=True))
        db.add(SiteShift(site_id="KOCP", shift="A", start_time=time(5), end_time=time(13), scheduled_hours=Decimal("8"), sequence_no=1, active=True))
        db.add(SiteShift(site_id="KOCP", shift="B", start_time=time(13), end_time=time(21), scheduled_hours=Decimal("8"), sequence_no=2, active=True))
        db.add(Site(site_id="SOCP", site_name="SOCP", short_name="SOCP", active=True))
        db.add(SiteHsdTransaction(
            transaction_id="OPEN",site_id="KOCP",operating_date=DAY,
            transaction_type="OPENING",litres=Decimal("10000"),entered_by="TEST",
            reference_no="Physical stock sheet",source_type="PORTAL",status="POSTED",version=1,
        ))
        db.commit()
    return engine


def asset(db, mid, ownership="HIRED", site="KOCP", effective=date(2026, 11, 3)):
    db.add(Equipment(machine_id=mid,type="Other",group="VEHICLE",
                     vehicle_no=f"OD09Z-{mid}",ownership=ownership,active=True))
    db.add(EquipmentSiteAssignment(machine_id=mid,site_id=site,
             effective_from=effective,ownership=ownership,active=True))
    db.commit()


def test_historical_kocp_hired_vehicle_allowed_but_other_owner_and_site_rejected():
    engine=database()
    with Session(engine) as db:
        asset(db,"137")
        asset(db,"135",ownership="NMTPL")
        asset(db,"139",site="SOCP")
        accepted,from_day=sites._kocp_hsd_equipment_eligibility(db,"137",DAY)
        assert accepted.machine_id=="137"
        assert from_day==date(2026,11,3)
        assert sites._kocp_hsd_equipment_eligibility(db,"135",DAY)==(None,None)
        assert sites._kocp_hsd_equipment_eligibility(db,"139",DAY)==(None,None)
        accepted2,from_day2=sites._kocp_hsd_equipment_eligibility(db,"137",date(2026,11,3))
        assert accepted2.machine_id=="137" and from_day2 is None
    engine.dispose()


def test_hired_fuel_post_is_audited_without_changing_master_dates(monkeypatch):
    engine=database()
    with Session(engine) as db:asset(db,"137")
    app=FastAPI()
    app.include_router(sites.router)

    def getdb():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[sites.get_db]=getdb
    monkeypatch.setattr(sites,"get_user",lambda db,request:SimpleNamespace(admin=True,login_id="TEST"))
    monkeypatch.setattr(sites,"require_site",lambda db,user,site:site)
    monkeypatch.setattr(sites,"require_permission",lambda *args:None)
    monkeypatch.setattr(sites,"csrf",lambda request:None)
    with TestClient(app) as client:
        posted=client.post("/api/sites/KOCP/hsd",json={
            "operatingDate":DAY.isoformat(),"shift":"A","transactionType":"ISSUE",
            "assetId":"137","assetType":"EQUIPMENT","litres":"48",
            "sourceType":"PORTAL","sourceRecordUid":"HSD-HIRED-137"
        })
        assert posted.status_code==200,posted.text
        assert posted.json()["historicalHired"] is True
        assert posted.json()["assignmentEffectiveFrom"]=="2026-11-03"
    with Session(engine) as db:
        assignment=db.scalar(select(EquipmentSiteAssignment).where(EquipmentSiteAssignment.machine_id=="137"))
        assert assignment.effective_from==date(2026,11,3)
        audit=db.scalar(select(SiteAuditLog).where(SiteAuditLog.entity_id==posted.json()["transactionId"]))
        assert '"historicalHiredAssignment": true' in audit.after_json
    engine.dispose()


def test_every_issued_vehicle_shows_with_from_to_and_shift(monkeypatch):
    engine=database()
    with Session(engine) as db:
        for i in range(1,16):
            mid=str(i)
            asset(db,mid,ownership="HIRED" if i%2 else "NMTPL", effective=DAY)
            db.add(SiteHsdTransaction(
                transaction_id=f"ISS-{i}",site_id="KOCP",operating_date=DAY,
                shift="A" if i<11 else "B",transaction_type="ISSUE",
                asset_type="EQUIPMENT",asset_id=mid,
                litres=Decimal(str(i*10)),entered_by="TEST",
                source_type="PORTAL",status="POSTED",version=1,
            ))
        db.add(SiteHsdTransaction(transaction_id="VOID-ISS",site_id="KOCP",
            operating_date=DAY,shift="A",transaction_type="ISSUE",asset_id="1",
            litres=Decimal("999"),entered_by="TEST",status="VOID",source_type="PORTAL",version=2))
        db.commit()
        monkeypatch.setattr(site_ops,"get_user",lambda db,request:SimpleNamespace(admin=True,login_id="TEST"))
        monkeypatch.setattr(site_ops,"require_site",lambda db,user,site:site)
        monkeypatch.setattr(site_ops,"_require_any",lambda *args:None)
        all_vehicles=site_ops.kocp_hsd_vehicle_report(object(),DAY,DAY,None,db)
        assert all_vehicles["vehicleCount"]==15
        assert len(all_vehicles["vehicles"])==15
        assert all_vehicles["issueCount"]==15
        assert Decimal(all_vehicles["totalLitres"])==Decimal("1200")
        assert all("OD09Z-" in x["vehicle"] for x in all_vehicles["vehicles"])
        assert len(all_vehicles["entries"])==15
        a_only=site_ops.kocp_hsd_vehicle_report(object(),DAY,DAY,"A",db)
        assert a_only["vehicleCount"]==10
        assert a_only["issueCount"]==10
        assert Decimal(a_only["totalLitres"])==Decimal("550")
    engine.dispose()


def test_full_vehicle_report_ui_includes_date_filters_and_export():
    code=(ROOT/"app/static/simple_field_v1.js").read_text("utf-8")
    assert "All HSD-consuming vehicles / equipment" in code
    assert "kocpHsdFrom" in code and "kocpHsdTo" in code
    assert "kocpHsdShift" in code
    assert "downloadKocpFuelVehicleCsv" in code
    assert "kocpFuelVehicleResults" in code
