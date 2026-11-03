"""KOCP HSD stock guard and admin audit regression tests."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.site_models import Site, SiteHsdTransaction, SiteAuditLog
from app.routers import sites
from app.services.kocp_hsd_stock import evaluate_hsd_stock, require_fuel_available

DAY = date(2026, 11, 3)


def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP", site_name="KOCP", short_name="KOCP", active=True))
        db.commit()
    return engine


def add_hsd(db, ident, typ, litres, *, entered_by="ADMIN", asset_id=None,
            supplier=None, day=DAY, status="POSTED"):
    db.add(SiteHsdTransaction(
        transaction_id=ident, site_id="KOCP", operating_date=day,
        shift=None if typ == "OPENING" else "A",
        transaction_type=typ, litres=Decimal(str(litres)),
        asset_id=asset_id, supplier=supplier,
        reference_no="Physical stock sheet" if typ == "OPENING" else "HSD reference",
        source_type="PORTAL", entered_by=entered_by,
        status=status, version=1,
    ))
    db.commit()


def app_client(monkeypatch, engine, admin=True):
    app = FastAPI()
    app.include_router(sites.router)

    def getdb():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[sites.get_db] = getdb
    monkeypatch.setattr(sites, "get_user", lambda db, request: SimpleNamespace(
        admin=admin, login_id="ADMIN" if admin else "OPERATOR"))
    monkeypatch.setattr(sites, "require_site", lambda db, user, site_id: site_id)
    monkeypatch.setattr(sites, "csrf", lambda request: None)
    monkeypatch.setattr(sites, "require_permission", lambda db, user, site_id, module, action: None)
    monkeypatch.setattr(sites, "_site_shift_active", lambda db, site, shift: shift == "A")
    monkeypatch.setattr(sites, "_site_equipment_assignment", lambda db, site, asset, day: bool(asset))
    return TestClient(app)


def issue_body(uid, litres):
    return {
        "operatingDate": DAY.isoformat(), "shift": "A",
        "transactionType": "ISSUE", "assetType": "EQUIPMENT", "assetId": "TIP-1",
        "litres": str(litres), "sourceType": "PORTAL", "sourceRecordUid": uid,
    }


def test_no_opening_blocks_fuel_issue_even_if_historical_issue_exists(monkeypatch):
    engine = database()
    with Session(engine) as db:
        add_hsd(db, "LEGACY-ISSUE", "ISSUE", "2778", asset_id="TIP-1")
    with app_client(monkeypatch, engine) as client:
        res = client.post("/api/sites/KOCP/hsd", json=issue_body("NEW-ISSUE", 1))
        assert res.status_code == 409
        assert "Opening stock" in res.json()["detail"]
    with Session(engine) as db:
        assert db.query(SiteHsdTransaction).count() == 1
    engine.dispose()


def test_opening_must_cover_historical_issues_and_limits_next_issue(monkeypatch):
    engine = database()
    with Session(engine) as db:
        add_hsd(db, "LEGACY-ISSUE", "ISSUE", "2778", asset_id="TIP-1")
    with app_client(monkeypatch, engine) as client:
        opening = {
            "operatingDate": DAY.isoformat(), "shift": None,
            "transactionType": "OPENING", "litres": "2000",
            "referenceNo": "Physical stock register 3 Nov",
        }
        denied = client.post("/api/sites/KOCP/hsd", json=opening)
        assert denied.status_code == 409
        assert "negative" in denied.json()["detail"]
        opening["litres"] = "3000"
        accepted = client.post("/api/sites/KOCP/hsd", json=opening)
        assert accepted.status_code == 200, accepted.text
        assert client.post("/api/sites/KOCP/hsd", json=issue_body("NO-STOCK", 223)).status_code == 409
        issue = client.post("/api/sites/KOCP/hsd", json=issue_body("JUST-ENOUGH", 222))
        assert issue.status_code == 200
        assert Decimal(issue.json()["remainingLitres"]) == Decimal("0")
        assert client.post("/api/sites/KOCP/hsd", json=issue_body("NONE-LEFT", 1)).status_code == 409
    engine.dispose()


def test_admin_can_correct_historical_issue_downward_without_opening(monkeypatch):
    engine = database()
    with Session(engine) as db:
        add_hsd(db, "MISTAKE", "ISSUE", 300, asset_id="TIP-1")
    with app_client(monkeypatch, engine) as client:
        result = client.post("/api/sites/KOCP/hsd/MISTAKE/correct", json={
            "action": "EDIT", "expectedVersion": 1, "reason": "Correct misread dispenser volume",
            "litres": "200", "operatingDate": DAY.isoformat(), "shift": "A",
            "assetId": "TIP-1",
        })
        assert result.status_code == 200, result.text
        assert result.json()["stockVerified"] is False
        retry = client.post("/api/sites/KOCP/hsd/MISTAKE/correct", json={
            "action": "VOID", "expectedVersion": 1, "reason": "Duplicate transaction recorded",
        })
        assert retry.status_code == 409
        void = client.post("/api/sites/KOCP/hsd/MISTAKE/correct", json={
            "action": "VOID", "expectedVersion": 2, "reason": "Transaction was a duplicate",
        })
        assert void.status_code == 200
    with Session(engine) as db:
        item = db.get(SiteHsdTransaction, "MISTAKE")
        assert item.status == "VOID"
        assert item.version == 3
        assert Decimal(str(item.litres)) == Decimal("200")
        logs = list(db.scalars(select(SiteAuditLog).where(
            SiteAuditLog.site_id == "KOCP",
            SiteAuditLog.entity_id == "MISTAKE",
        )))
        assert {x.action for x in logs} == {"EDIT_HSD", "VOID_HSD"}
        assert all(x.reason for x in logs)
    engine.dispose()


def test_non_admin_cannot_edit_or_void_fuel(monkeypatch):
    engine = database()
    with Session(engine) as db:
        add_hsd(db, "PORTAL-ISSUE", "ISSUE", 300, asset_id="TIP-1")
    with app_client(monkeypatch, engine, admin=False) as client:
        res = client.post("/api/sites/KOCP/hsd/PORTAL-ISSUE/correct", json={
            "action": "VOID", "expectedVersion": 1, "reason": "Operator tries to delete fuel",
        })
        assert res.status_code == 403
    engine.dispose()


def test_stock_helper_only_counts_posted_and_checks_daily_negative():
    engine = database()
    with Session(engine) as db:
        add_hsd(db, "OPEN", "OPENING", "50")
        add_hsd(db, "ISSUE", "ISSUE", "40", asset_id="TIP-1")
        add_hsd(db, "VOID", "ISSUE", "100", asset_id="TIP-1", status="VOID")
        state = evaluate_hsd_stock(db, "KOCP", as_of=DAY)
        assert state["verified"] is True
        assert state["balance"] == Decimal("10")
        assert require_fuel_available(db, "KOCP", DAY, Decimal("10")) == Decimal("0")
        with pytest.raises(HTTPException) as exc:
            require_fuel_available(db, "KOCP", DAY, Decimal("11"))
        assert exc.value.status_code == 409
    engine.dispose()
