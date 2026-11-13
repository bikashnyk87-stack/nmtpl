"""KOCP MCL class options and factor writes must use Equipment Masters, never static brands."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Equipment
from app.site_models import (
    Site, EquipmentSiteAssignment, SiteLocation, SiteMaterial, SiteWeightFactor,
)
from app.site_schemas import WeightFactorIn, WeightFactorDecisionIn
from app.routers import sites
from app.services.kocp_equipment import kocp_vehicle_classes
from app.services.kocp_factor_rules import choose_point_factor

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 11, 13)


def db_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Site(site_id="KOCP", site_name="KOCP", short_name="KOCP", active=True),
            Site(site_id="SOCP", site_name="SOCP", short_name="SOCP", active=True),
            SiteLocation(site_location_id="DEST", site_id="KOCP",
                         code="DEST", name="Stock yard", active=True),
            SiteMaterial(site_material_id="COAL", site_id="KOCP",
                         code="COAL", name="Coal", default_unit="MT", active=True),
        ])
        db.commit()
    return engine


def add_vehicle(db, mid, cls, *, site="KOCP", active=True, model=""):
    db.add(Equipment(machine_id=mid, type=cls, make_model=model,
                     group="COAL", active=active))
    db.add(EquipmentSiteAssignment(machine_id=mid, site_id=site,
            effective_from=DAY, active=True, ownership="OWN"))
    db.commit()


def test_empty_equipment_master_does_not_create_any_class():
    engine = db_engine()
    with Session(engine) as db:
        assert sites._kocp_master_mcl_vehicle_classes(db) == []
    engine.dispose()


def test_classes_come_only_from_active_ko_cp_transport_masters_and_are_deduplicated():
    engine = db_engine()
    with Session(engine) as db:
        add_vehicle(db, "E1", "EICHER TIPPER")
        add_vehicle(db, "E2", " eicher   tipper ")
        add_vehicle(db, "B1", "BHARAT BENZ TIPPER")
        add_vehicle(db, "V1", "VOLVO TIPPER")
        add_vehicle(db, "T1", "TATA TIPPER", active=False)
        add_vehicle(db, "S1", "ASHOK LEYLAND TIPPER", site="SOCP")
        add_vehicle(db, "L1", "Tripper", model="L150H")
        assert sites._kocp_master_mcl_vehicle_classes(db) == [
            "BHARAT BENZ TIPPER", "EICHER TIPPER", "VOLVO TIPPER"
        ]
        # A class is added / removed only through equipment master changes.
        e = db.get(Equipment, "T1")
        e.active = True
        db.commit()
        assert "TATA TIPPER" in sites._kocp_master_mcl_vehicle_classes(db)
        e.active = False
        db.commit()
        assert "TATA TIPPER" not in sites._kocp_master_mcl_vehicle_classes(db)
    engine.dispose()


def test_factor_matching_never_generates_brand_aliases_from_model_or_type():
    assert kocp_vehicle_classes("EICHER TIPPER", "COAL", "PRO 8035XML") == {"EICHER TIPPER"}
    assert kocp_vehicle_classes("BHARAT BENZ TIPPER", "OB") == {"BHARAT BENZ TIPPER"}
    base = dict(
        status="APPROVED", factor_type="COAL_AVG_MT_PER_TRIP",
        effective_from=DAY, effective_to=None, operating_date=None,
        destination_location_id="DEST", route_id=None,
        material_id="COAL", shift=None, factor_value=Decimal("35.92"),
    )
    class_factor = SimpleNamespace(**base, vehicle_class="EICHER TIPPER")
    invented_factor = SimpleNamespace(**base, vehicle_class="EICHER")
    params = dict(
        operating_day=DAY, shift="A", destination_id="DEST", route_id=None,
        material_id="COAL", vehicle_type="EICHER TIPPER",
        vehicle_group="COAL", vehicle_model="PRO 8035XML"
    )
    assert choose_point_factor([class_factor], **params) is class_factor
    with pytest.raises(HTTPException) as err:
        choose_point_factor([invented_factor], **params)
    assert err.value.status_code == 409


def test_server_rejects_non_master_factor_class_and_accepts_exact_master(monkeypatch):
    engine = db_engine()
    with Session(engine) as db:
        add_vehicle(db, "E1", "EICHER TIPPER")
        monkeypatch.setattr(sites, "csrf", lambda request: None)
        monkeypatch.setattr(sites, "get_user", lambda db,request:
                            SimpleNamespace(admin=True,login_id="ADMIN"))
        monkeypatch.setattr(sites, "require_site", lambda db,user,site_id: site_id)
        monkeypatch.setattr(sites, "require_permission", lambda *args: None)
        values = dict(
            factorType="COAL_AVG_MT_PER_TRIP", factorValue=Decimal("35.92"),
            factorUnit="MT/TRIP", effectiveFrom=DAY,
            destinationLocationId="DEST", materialId="COAL",
            sourceOrg="DAILY_REPORT", referenceNo="Approved sheet 1",
        )
        with pytest.raises(HTTPException) as err:
            sites.create_weight_factor("KOCP", WeightFactorIn(
                **values, vehicleClass="EICHER"
            ), object(), db)
        assert err.value.status_code == 422
        accepted = sites.create_weight_factor("KOCP", WeightFactorIn(
            **values, vehicleClass=" eicher  tipper "
        ), object(), db)
        assert accepted["status"] == "DRAFT"
        factor = db.get(SiteWeightFactor, accepted["factorId"])
        assert factor.vehicle_class == "EICHER TIPPER"
        db.get(Equipment, "E1").active = False
        db.commit()
        with pytest.raises(HTTPException) as blocked:
            sites.decide_weight_factor("KOCP", accepted["factorId"],
                WeightFactorDecisionIn(action="APPROVE"), object(), db)
        assert blocked.value.status_code == 409
    engine.dispose()


def test_ui_and_master_editor_have_no_hardcoded_mcl_brands():
    backend = (ROOT / "app/routers/sites.py").read_text("utf-8")
    equip = (ROOT / "app/services/kocp_equipment.py").read_text("utf-8")
    ui = (ROOT / "app/static/kocp_pointwise.js").read_text("utf-8")
    masters = (ROOT / "app/static/kocp_masters_compact.js").read_text("utf-8")
    assert "values = {\"EICHER\", \"BHARAT BENZ\"" not in backend
    assert 'options=new Set([\'EICHER\'' not in ui
    assert 'for brand in ("EICHER"' not in equip
    assert "koFactorClassesFromEquipment" not in ui
    assert "factor-vehicle-classes" in ui
    assert "equipment_class" in masters
    assert "kcmExistingVehicleTypes" in masters
    assert "Physical machine type / MCL vehicle class" in masters
