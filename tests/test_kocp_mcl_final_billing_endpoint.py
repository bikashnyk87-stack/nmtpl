"""Certified KOCP monthly average billing: draft, approval, and immutable snapshots."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Equipment
from app.site_models import Site, SiteMaterial, SiteTrip, SiteWeightFactor, SiteBillingReconciliation
from app.routers import site_ops

START = date(2026, 11, 1)
END = date(2026, 11, 30)


def setup_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP", site_name="KOCP", short_name="KOCP", active=True))
        db.add(SiteMaterial(site_material_id="COAL",site_id="KOCP",
                            name="Coal",code="COAL",default_unit="MT",active=True))
        db.add(Equipment(machine_id="E1",type="EICHER TIPPER",group="COAL",
                         ownership="NMTPL",active=True))
        db.add(SiteTrip(trip_id="T1",site_id="KOCP",operating_date=START,
                        shift="A",material_id="COAL",vehicle_id="E1",
                        destination_location_id="KN5",quantity_mt=Decimal("33.44"),
                        status="POSTED",entered_by="MIS"))
        db.add(SiteWeightFactor(
            factor_id="MCL-M1",site_id="KOCP",factor_type="COAL_AVG_MT_PER_TRIP",
            factor_value=Decimal("35.92"),factor_unit="MT/TRIP",material_id="COAL",
            destination_location_id="KN5",vehicle_class="EICHER",status="APPROVED",
            source_org="MCL_MONTHLY",reference_no="MCL November approved",
            effective_from=START,effective_to=END,entered_by="ADMIN",
        ))
        db.commit()
    return engine


def test_month_end_factor_controls_billable_not_operational(monkeypatch):
    engine=setup_db()
    app=FastAPI()
    app.include_router(site_ops.router)
    def getdb():
        with Session(engine) as db: yield db
    app.dependency_overrides[site_ops.get_db]=getdb
    monkeypatch.setattr(site_ops,"get_user",lambda db,req:SimpleNamespace(admin=True,login_id="ADMIN"))
    monkeypatch.setattr(site_ops,"require_site",lambda db,user,site:site)
    monkeypatch.setattr(site_ops,"require_permission",lambda *a:None)
    monkeypatch.setattr(site_ops,"csrf",lambda *a:None)
    with TestClient(app) as client:
        params={"period_start":START.isoformat(),"period_end":END.isoformat(),
                "material_id":"COAL"}
        r=client.post("/api/site-ops/KOCP/billing/build",params=params)
        assert r.status_code==200,r.text
        assert r.json()["certified"] is True
        assert r.json()["billingBasis"]=="MCL_MONTHLY_AVERAGE"
        bid=r.json()["billingId"]
        with Session(engine) as db:
            bill=db.get(SiteBillingReconciliation,bid)
            assert bill.operational_mt==Decimal("33.440")
            assert bill.billable_mt==Decimal("35.920")
            assert bill.factor_snapshot_json
            assert db.get(SiteTrip,"T1").quantity_mt==Decimal("33.440")
        approval=client.post(f"/api/site-ops/KOCP/billing/{bid}/decision",
                             json={"action":"APPROVE","reason":"MCL checked"})
        assert approval.status_code==200,approval.text
        assert approval.json()["status"]=="APPROVED"
    engine.dispose()


def test_added_trip_requires_rebuild_before_monthly_approval(monkeypatch):
    engine=setup_db()
    app=FastAPI()
    app.include_router(site_ops.router)
    def getdb():
        with Session(engine) as db:yield db
    app.dependency_overrides[site_ops.get_db]=getdb
    monkeypatch.setattr(site_ops,"get_user",lambda db,req:SimpleNamespace(admin=True,login_id="ADMIN"))
    monkeypatch.setattr(site_ops,"require_site",lambda db,user,site:site)
    monkeypatch.setattr(site_ops,"require_permission",lambda *a:None)
    monkeypatch.setattr(site_ops,"csrf",lambda *a:None)
    with TestClient(app) as client:
        r=client.post("/api/site-ops/KOCP/billing/build",params={
            "period_start":START.isoformat(),"period_end":END.isoformat(),
            "material_id":"COAL"})
        assert r.status_code==200,r.text
        bid=r.json()["billingId"]
        with Session(engine) as db:
            db.add(SiteTrip(trip_id="T2",site_id="KOCP",operating_date=START,
                            shift="B",material_id="COAL",vehicle_id="E1",
                            destination_location_id="KN5",quantity_mt=Decimal("33.44"),
                            status="POSTED",entered_by="MIS"))
            db.commit()
        approval=client.post(f"/api/site-ops/KOCP/billing/{bid}/decision",
                             json={"action":"APPROVE","reason":"Check after extra trips"})
        assert approval.status_code==409
        assert "Rebuild" in approval.json()["detail"]
    engine.dispose()
