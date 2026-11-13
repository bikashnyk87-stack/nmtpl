"""Single-entry KOCP masters must work without importing an Excel file."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.site_models import Site, SiteLocation, SiteMaterial, SiteMovementRoute
from app.routers import site_routes, sites, site_material_types

ROOT = Path(__file__).resolve().parents[1]


def engine_for_test():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP",site_name="KOCP",short_name="KOCP",active=True))
        db.commit()
    return engine


def authorize(monkeypatch):
    user = SimpleNamespace(admin=True, login_id="TEST-ADMIN")
    monkeypatch.setattr(site_routes, "csrf", lambda req: None)
    monkeypatch.setattr(site_routes, "_access", lambda db,req,site,action="VIEW": user)
    monkeypatch.setattr(sites, "csrf", lambda req: None)
    monkeypatch.setattr(sites, "get_user", lambda db,req: user)
    monkeypatch.setattr(sites, "require_site", lambda db,user,site: site)
    monkeypatch.setattr(sites, "has_permission", lambda *args: True)


def test_create_coal_route_reuses_location_and_duplicate_is_blocked(monkeypatch):
    authorize(monkeypatch)
    engine = engine_for_test()
    with Session(engine) as db:
        first = site_routes.create_route_record("KOCP", "COAL", {
            "group": "Coal Stock", "destination": "New Yard",
            "category": "Stock", "distanceRange": "1-2/3-4", "active": True,
        }, object(), db)
        assert first["created"] is True
        result = site_routes.create_route_record("KOCP", "COAL", {
            "group": "Coal Stock", "destination": "new  yard",
            "category": "Stock", "distanceRange": "2-3/3-4", "active": True,
        }, object(), db)
        r1 = db.get(SiteMovementRoute, first["record"]["routeId"])
        r2 = db.get(SiteMovementRoute, result["record"]["routeId"])
        assert r1.destination_location_id == r2.destination_location_id
        assert db.scalar(select(func.count()).select_from(SiteLocation)) == 1
        with pytest.raises(HTTPException) as exc:
            site_routes.create_route_record("KOCP", "COAL", {
                "group": "Coal Stock", "destination": "NEW YARD",
                "category": "Stock", "distanceRange": "1-2/3-4",
            }, object(), db)
        assert exc.value.status_code == 409
    engine.dispose()


def test_ob_route_creates_source_and_reuses_existing_destination(monkeypatch):
    authorize(monkeypatch)
    engine = engine_for_test()
    with Session(engine) as db:
        site_routes.create_route_record("KOCP", "COAL", {
            "group":"Coal Stock", "destination":"Dump Yard",
            "category":"Stock", "distanceRange":"1-2",
        }, object(), db)
        result = site_routes.create_route_record("KOCP", "OB", {
            "group":"Working Place to Dump", "source":"Working Face",
            "destination":"Dump Yard", "category":"Soft OB",
            "distanceRange":"2-3",
        }, object(), db)
        assert result["record"]["sourceLocationId"]
        assert db.scalar(select(func.count()).select_from(SiteLocation)) == 2
        with pytest.raises(HTTPException) as exc:
            site_routes.create_route_record("KOCP","OB",{
                "group":"Working Place to Dump","destination":"Dump Yard",
                "category":"Soft OB","distanceRange":"2-3",
            },object(),db)
        assert exc.value.status_code == 422
    engine.dispose()


def test_add_material_is_in_operational_catalog_and_duplicate_code_is_rejected(monkeypatch):
    authorize(monkeypatch)
    engine = engine_for_test()
    with Session(engine) as db:
        body = {
            "createOnly":True, "code":"TEST-MT", "name":"Test Additional Coal",
            "materialGroup":"COAL", "defaultUnit":"MT", "billableUnit":"MT",
            "active":True,
        }
        result=sites.save_single_master_record("KOCP","MATERIAL",body,object(),db)
        assert result["created"]
        catalog=site_material_types._catalog(db)
        items=[x for x in catalog["COAL"] if x["storedCode"]=="TEST-MT"]
        assert len(items)==1 and items[0]["active"] is True
        assert items[0]["materialId"] == "KOCP:TEST-MT"
        with pytest.raises(HTTPException) as exc:
            sites.save_single_master_record("KOCP","MATERIAL",
                {**body,"name":"Wrong overwrite"},object(),db)
        assert exc.value.status_code == 409
        assert db.get(SiteMaterial,"KOCP:TEST-MT").name=="Test Additional Coal"
    engine.dispose()


def test_add_location_rejects_duplicate_name_even_with_different_code(monkeypatch):
    authorize(monkeypatch)
    engine = engine_for_test()
    with Session(engine) as db:
        body = {"createOnly":True,"code":"YARD1","name":"Mine Dispatch Yard",
                "locationType":"UNLOADING","active":True}
        result=sites.save_single_master_record("KOCP","LOCATION",body,object(),db)
        assert result["created"]
        with pytest.raises(HTTPException) as exc:
            sites.save_single_master_record("KOCP","LOCATION",
                {**body,"code":"YARD2","name":"mine  dispatch yard"},object(),db)
        assert exc.value.status_code == 409
        assert db.scalar(select(func.count()).select_from(SiteLocation)) == 1
    engine.dispose()


def test_single_entry_ui_wired_for_all_masters_and_excel_remains_optional():
    js=(ROOT/"app/static/kocp_masters_compact.js").read_text("utf-8")
    route=(ROOT/"app/routers/site_routes.py").read_text("utf-8")
    assert "'+ Add Single Entry'" in js
    assert "vm.tab!=='HISTORY'" in js
    assert "vm.tab==='LOCATIONS'?'LOCATION':vm.tab" in js
    assert "'/api/sites/KOCP/routes/'+vm.tab+'/records'" in js
    assert "body.createOnly=!vm.edit" in js
    assert "'Import Excel'" in js
    assert "vm.existingMaterials.filter" in js
    assert "field('source','From / source location *'" in js
    assert '@router.post("/{site_id}/routes/{kind}/records")' in route
