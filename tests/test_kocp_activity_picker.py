"""KOCP production pickers: strict Coal/OB isolation, stable identity and full search."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Equipment
from app.site_models import EquipmentSiteAssignment, Site
from app.routers import site_ops
from app.services.kocp_equipment import (
    kocp_asset_allowed, kocp_role_allowed, kocp_asset_display,
)


def test_activity_classification_and_role():
    assert kocp_asset_allowed("COAL", "COAL")
    assert not kocp_asset_allowed("OB", "COAL")
    assert kocp_asset_allowed("OB/COAL (BOTH)", "COAL")
    assert kocp_asset_allowed("OB/COAL (BOTH)", "OB")
    assert not kocp_asset_allowed("KOCP", "COAL")
    assert kocp_role_allowed("EXCAVATOR VOLVO-480", "LOADING")
    assert kocp_role_allowed("TATA HITACHI-3200", "LOADING")
    assert kocp_role_allowed("EICHER TIPPER", "TRANSPORT")
    assert not kocp_role_allowed("EXCAVATOR VOLVO-480", "TRANSPORT")
    assert not kocp_role_allowed("DOZER", "LOADING")


def test_door_number_and_rented_reference_not_ambiguous():
    first=kocp_asset_display("100", "504", "EC480DL", "NMTPL", None, "EXCAVATOR VOLVO-480")
    second=kocp_asset_display("101", "505", "EC480DL", "NMTPL", None, "EXCAVATOR VOLVO-480")
    assert first[0] != second[0]
    assert "504" in first[0] and "505" in second[0]
    rental=kocp_asset_display("55", None, "OD-35G-0369", "BEHERA ENTERPRISES", None, "LIUGONG LOADER")
    assert rental[2] == "R-55"
    assert "R-55" in rental[0]
    assert "BEHERA ENTERPRISES" in rental[1]


def test_kocp_search_returns_all_eligible_and_hides_wrong_activity(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP",site_name="KOCP",short_name="KOCP",active=True))
        for i in range(1, 132):
            activity="COAL" if i<=58 else "OB" if i<=107 else "OB/COAL (BOTH)" if i<=124 else "KOCP"
            typ="EICHER TIPPER" if i<=50 or 59<=i<=95 else "VOLVO LOADER" if i<=58 or 96<=i<=107 else "DOZER"
            db.add(Equipment(machine_id=str(i),door_no=str(i),vehicle_no="EC480DL" if typ=="VOLVO LOADER" else f"OD-{i:03}",type=typ,group=activity,ownership="NMTPL",active=True))
            db.add(EquipmentSiteAssignment(machine_id=str(i),site_id="KOCP",effective_from=__import__("datetime").date(2026,10,1),active=True))
        db.commit()
    app=FastAPI()
    app.include_router(site_ops.router)
    def getdb():
        with Session(engine) as db:yield db
    app.dependency_overrides[site_ops.get_db]=getdb
    monkeypatch.setattr(site_ops,"get_user",lambda db,request:SimpleNamespace(admin=True,login_id="TEST"))
    monkeypatch.setattr(site_ops,"require_site",lambda db,user,site_id:site_id)
    with TestClient(app) as client:
        coal=client.get("/api/site-ops/KOCP/lookups",params={"kind":"ASSET","activity":"COAL","role":"TRANSPORT","limit":200})
        assert coal.status_code==200,coal.text
        items=coal.json()
        assert len(items)==50
        assert all(x["group"]=="COAL" for x in items)
        assert len({x["id"] for x in items})==len(items)
        assert all("Door" in x["label"] for x in items)
        ob=client.get("/api/site-ops/KOCP/lookups",params={"kind":"ASSET","activity":"OB","role":"LOADING","limit":200})
        assert ob.status_code==200,ob.text
        assert len(ob.json())==12
        assert all(x["group"]=="OB" for x in ob.json())
        lookup_all=client.get("/api/site-ops/KOCP/lookups",params={"kind":"ASSET","limit":200})
        assert lookup_all.status_code==200
        assert len(lookup_all.json())==131
    engine.dispose()


def test_ui_keeps_unsaved_rows_and_expands_hmr_for_used_machines():
    from pathlib import Path
    ui=(Path(__file__).resolve().parents[1]/"app/static/simple_field_v1.js").read_text("utf8")
    assert "function addSimpleTripRows(amount)" in ui
    assert "parent.insertAdjacentHTML('beforeend',tripGridRows('TRIP',amount,start))" in ui
    assert "parent.insertAdjacentHTML('beforeend',kocpHmrRows(1,i))" in ui
    assert "params.set('activity',activity)" in ui
    assert "limit:kocpAsset?'200':'40'" in ui
    assert "if(activity){params.set('activity',activity);params.set('role',role)}" in ui
