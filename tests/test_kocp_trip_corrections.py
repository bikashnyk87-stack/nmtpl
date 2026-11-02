"""KOCP trip correction/void regression coverage: audit, version and billing locks."""
from datetime import date, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.routers import site_ops
from app.site_models import Site, SiteAuditLog, SiteTrip, SiteBillingReconciliation


def test_kocp_trip_void_is_audited_and_version_locked(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP", site_name="KOCP", short_name="KOCP", active=True))
        db.add(SiteTrip(
            trip_id="TRIP-KOCP-TEST", site_id="KOCP", operating_date=date(2026, 11, 2),
            shift="A", event_at=datetime(2026, 11, 2, 5), source_type="PORTAL_SIMPLE",
            source_record_uid="WEB-TEST-1", status="POSTED", entered_by="TEST", version=1,
        ))
        db.commit()

    app = FastAPI()
    app.include_router(site_ops.router)

    def getdb():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[site_ops.get_db] = getdb
    monkeypatch.setattr(site_ops, "get_user", lambda db, request: SimpleNamespace(admin=True, login_id="TEST"))
    monkeypatch.setattr(site_ops, "require_site", lambda db, user, site_id: site_id)
    monkeypatch.setattr(site_ops, "csrf", lambda request: None)

    endpoint = "/api/site-ops/KOCP/trips/TRIP-KOCP-TEST/correct"
    with TestClient(app) as client:
        short_reason = client.post(endpoint, json={
            "action": "VOID", "expectedVersion": 1, "reason": "bad",
        })
        assert short_reason.status_code == 422

        response = client.post(endpoint, json={
            "action": "VOID", "expectedVersion": 1,
            "reason": "Duplicated same vehicle trip entry",
        })
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "VOID"
        assert response.json()["version"] == 2

        retry = client.post(endpoint, json={
            "action": "VOID", "expectedVersion": 1,
            "reason": "Duplicated same vehicle trip entry",
        })
        assert retry.status_code == 409

    with Session(engine) as db:
        trip = db.get(SiteTrip, "TRIP-KOCP-TEST")
        assert trip.status == "VOID"
        assert trip.version == 2
        logs = list(db.scalars(select(SiteAuditLog).where(
            SiteAuditLog.site_id == "KOCP",
            SiteAuditLog.action == "VOID_KOCP_TRIP",
        )))
        assert len(logs) == 1
        assert logs[0].reason == "Duplicated same vehicle trip entry"
    engine.dispose()


def test_approved_billing_period_locks_trip_void(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP", site_name="KOCP", short_name="KOCP", active=True))
        db.add(SiteTrip(
            trip_id="TRIP-KOCP-LOCKED", site_id="KOCP", operating_date=date(2026, 11, 2),
            shift="A", event_at=datetime(2026, 11, 2, 5), source_type="PORTAL_SIMPLE",
            source_record_uid="WEB-TEST-LOCK", status="POSTED", entered_by="TEST", version=1,
        ))
        db.add(SiteBillingReconciliation(
            billing_id="BILL-KOCP-TEST", site_id="KOCP", period_start=date(2026, 11, 1),
            period_end=date(2026, 11, 30), status="APPROVED", created_by="TEST",
        ))
        db.commit()
    app = FastAPI()
    app.include_router(site_ops.router)

    def getdb():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[site_ops.get_db] = getdb
    monkeypatch.setattr(site_ops, "get_user", lambda db, request: SimpleNamespace(admin=True, login_id="TEST"))
    monkeypatch.setattr(site_ops, "require_site", lambda db, user, site_id: site_id)
    monkeypatch.setattr(site_ops, "csrf", lambda request: None)
    with TestClient(app) as client:
        response = client.post("/api/site-ops/KOCP/trips/TRIP-KOCP-LOCKED/correct", json={
            "action": "VOID", "expectedVersion": 1, "reason": "Duplicated trip in locked billing",
        })
        assert response.status_code == 409
    with Session(engine) as db:
        assert db.get(SiteTrip, "TRIP-KOCP-LOCKED").status == "POSTED"
    engine.dispose()
