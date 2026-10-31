"""KOCP one-time fuel opening and colour dashboard regression tests."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.site_models import Site, SiteHsdTransaction
from app.site_schemas import SiteHsdTransactionIn
from app.routers import sites, site_ops

ROOT = Path(__file__).resolve().parents[1]


def db_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def user_and_context(monkeypatch):
    actor = SimpleNamespace(admin=True, login_id="tester")
    monkeypatch.setattr(sites, "csrf", lambda request: None)
    monkeypatch.setattr(sites, "get_user", lambda db, request: actor)
    monkeypatch.setattr(sites, "require_site", lambda db, user, site_id: site_id)
    monkeypatch.setattr(sites, "require_permission", lambda *args: None)
    monkeypatch.setattr(site_ops, "get_user", lambda db, request: actor)
    monkeypatch.setattr(site_ops, "require_site", lambda db, user, site_id: site_id)
    monkeypatch.setattr(site_ops, "resolve_site_context",
                        lambda db, site_id: SimpleNamespace(operating_date=date(2026, 10, 31)))


def opening_payload(amount=Decimal("250.500"), ref="STOCK-SHEET-001", source_uid="seed1"):
    return SiteHsdTransactionIn(
        operatingDate=date(2026,10,31), transactionType="OPENING", shift=None,
        litres=amount, referenceNo=ref, sourceRecordUid=source_uid,
        sourceType="PORTAL")


def test_opening_once_then_ledger_stock_from_posted_movements(monkeypatch):
    engine = db_engine()
    user_and_context(monkeypatch)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP", site_name="KOCP", short_name="KOCP", active=True))
        db.commit()
        saved = sites.create_hsd_transaction("KOCP", opening_payload(), object(), db)
        assert saved["ok"]
        initial = db.scalar(select(SiteHsdTransaction).where(
            SiteHsdTransaction.transaction_type=="OPENING"))
        assert initial.shift is None
        assert initial.litres == Decimal("250.500")
        assert initial.reference_no == "STOCK-SHEET-001"
        with pytest.raises(HTTPException) as exc:
            sites.create_hsd_transaction(
                "KOCP",opening_payload(Decimal("99"),"ANOTHER","seed2"),object(),db)
        assert exc.value.status_code == 409
        # A retry of the same request must return its original ID.
        retry = sites.create_hsd_transaction("KOCP",opening_payload(),object(),db)
        assert retry["idempotent"] is True
        for idx, kind, litres in [(1,"RECEIPT",Decimal("100")),(2,"ISSUE",Decimal("30"))]:
            db.add(SiteHsdTransaction(
                transaction_id=f"F-{idx}",site_id="KOCP",
                operating_date=date(2026,10,31),shift="A",
                transaction_type=kind,litres=litres,
                entered_by="tester",source_type="TEST",status="POSTED"))
        db.commit()
        dashboard = site_ops.fuel_summary("KOCP",object(),date(2026,10,1),date(2026,10,31),db)
        assert dashboard["openingBalance"]["litres"] == 250.5
        assert dashboard["openingBalance"]["reference"] == "STOCK-SHEET-001"
        assert dashboard["stockBalance"] == 320.5
        assert dashboard["periodTotals"]["receiptL"] == 100
        assert dashboard["periodTotals"]["issueL"] == 30
        assert dashboard["periodTotals"]["netMovementL"] == 70
        assert db.scalar(select(func.count()).select_from(SiteHsdTransaction)) == 3
    engine.dispose()


def test_zero_opening_allowed_but_unverified_or_duplicate_rejected(monkeypatch):
    engine = db_engine()
    user_and_context(monkeypatch)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP",site_name="KOCP",short_name="KOCP",active=True))
        db.commit()
        with pytest.raises(HTTPException) as exc:
            sites.create_hsd_transaction("KOCP",opening_payload(ref=""),object(),db)
        assert exc.value.status_code == 422
        with pytest.raises(HTTPException) as exc:
            sites.create_hsd_transaction("KOCP",opening_payload(amount=Decimal("-1")),object(),db)
        assert exc.value.status_code == 422
        assert sites.create_hsd_transaction(
            "KOCP", opening_payload(amount=Decimal("0")), object(), db)["ok"]
        result = site_ops.fuel_summary("KOCP",object(),date(2026,10,1),date(2026,10,31),db)
        assert result["stockBalance"] == 0
    engine.dispose()


def test_unclassified_adjustments_block_calculated_stock(monkeypatch):
    engine = db_engine()
    user_and_context(monkeypatch)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP",site_name="KOCP",short_name="KOCP",active=True))
        db.add(SiteHsdTransaction(transaction_id="O1",site_id="KOCP",
            operating_date=date(2026,10,1),transaction_type="OPENING",
            litres=Decimal("200"),reference_no="DOC",entered_by="tester",status="POSTED"))
        db.add(SiteHsdTransaction(transaction_id="A1",site_id="KOCP",
            operating_date=date(2026,10,15),transaction_type="ADJUSTMENT",
            litres=Decimal("10"),entered_by="tester",status="POSTED"))
        db.commit()
        result=site_ops.fuel_summary("KOCP",object(),date(2026,10,1),date(2026,10,31),db)
        assert result["openingBalance"]["litres"] == 200
        assert result["stockBalance"] is None
        assert "adjustments" in result["stockNote"]
    engine.dispose()


def test_opening_entry_ui_and_dashboard_palette():
    js=(ROOT/"app/static/simple_field_v1.js").read_text("utf-8")
    css=(ROOT/"app/static/simple_field_v1.css").read_text("utf-8")
    html=(ROOT/"app/static/site.html").read_text("utf-8")
    assert "tab('OPENING','Opening Balance')" in js
    assert "function openHsdOpening()" in js
    assert "async function saveHsdOpening()" in js
    assert "stock-verification" not in js or "hsdOpenRef" in js
    assert "sourceRecordUid:'KOCP-OPENING-'+date" in js
    assert "Calculated Stock" in js and "Opening Stock" in js
    assert ".ops-theme-kocp .ops-dashboard-top" in css
    assert "#15325b" in css and "#fff0cc" in css and "#d9f7e9" in css
    assert "kocp-compact-receipt-live-r8" in html
    p=subprocess.run(["node","--check",str(ROOT/"app/static/simple_field_v1.js")],
        capture_output=True,text=True,timeout=20)
    assert p.returncode == 0,p.stderr
