"""Daily and final MCL average separation, vehicle categories, and input UX."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Equipment
from app.site_models import Site, SiteTrip, SiteWeightFactor
from app.services.kocp_equipment import (
    kocp_equipment_category, kocp_role_allowed, kocp_ownership_category,
    kocp_vehicle_classes,
)
from app.services.kocp_factor_rules import choose_point_factor
from app.services.kocp_monthly_billing import month_end_factor_reconciliation

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 11, 1)
END = date(2026, 11, 30)


def factor(name, source="DAILY_REPORT", vehicle_class="EICHER", value="35.92"):
    return SimpleNamespace(
        factor_id=name, status="APPROVED", source_org=source,
        effective_from=DAY, effective_to=END, operating_date=None, shift=None,
        destination_location_id="KN5", route_id=None, material_id="COAL",
        vehicle_class=vehicle_class, factor_value=Decimal(value)
    )


def params():
    return dict(
        operating_day=DAY, shift="A", destination_id="KN5",
        route_id=None, material_id="COAL",
        vehicle_type="EICHER TIPPER", vehicle_group="COAL",
        vehicle_model="PRO 8035XML"
    )


def test_volvo_l150h_is_loader_not_tripper_even_if_master_type_wrong():
    assert kocp_equipment_category("Tripper", "L150H") == "LOADER"
    assert kocp_role_allowed("Tripper", "LOADING", "L150H")
    assert not kocp_role_allowed("Tripper", "TRANSPORT", "L150H")
    assert kocp_role_allowed("VOLVO TIPPER", "TRANSPORT", "VH12W")
    assert kocp_equipment_category("EXCAVATOR VOLVO-480", "EC480DL") == "EXCAVATOR"


def test_ownership_aliases_are_canonical_without_rewriting_master():
    assert kocp_ownership_category("OWN") == "OWN"
    assert kocp_ownership_category("NMTPL") == "OWN"
    assert kocp_ownership_category("HIRED") == "HIRED"
    assert kocp_ownership_category("GMPL") == "THIRD PARTY"


def test_eicher_tata_and_bharat_benz_are_valid_class_factors():
    assert "EICHER" in kocp_vehicle_classes("EICHER TIPPER", "COAL", "PRO 8035XML")
    assert "BHARAT BENZ" in kocp_vehicle_classes("BHARAT BENZ TIPPER", "COAL")
    assert "TATA" in kocp_vehicle_classes("TATA TIPPER", "OB")


def test_operational_factor_cannot_use_final_monthly_factor():
    daily = factor("DAILY", value="33.44")
    final = factor("FINAL", source="MCL_MONTHLY", value="35.92")
    assert choose_point_factor([daily, final], **params()).factor_id == "DAILY"
    assert choose_point_factor(
        [daily, final], **params(), allowed_sources=("MCL_MONTHLY",)
    ).factor_id == "FINAL"
    with pytest.raises(HTTPException) as e:
        choose_point_factor([final], **params())
    assert e.value.status_code == 409


def test_monthly_billing_revalues_trips_without_changing_operational_rows():
    engine = create_engine("sqlite://",
        connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP", site_name="KOCP", short_name="KOCP", active=True))
        db.add(Equipment(machine_id="E1", type="EICHER TIPPER", group="COAL",
                         make_model="PRO 8035XML", active=True))
        db.add(Equipment(machine_id="B1", type="BHARAT BENZ TIPPER", group="COAL",
                         make_model="3532 CM", active=True))
        for mid,qty in [("E1","33.44"),("B1","35.92")]:
            db.add(SiteTrip(
                trip_id="TRIP-"+mid, site_id="KOCP", operating_date=DAY,
                shift="A", vehicle_id=mid, material_id="COAL",
                destination_location_id="KN5", route_id=None,
                quantity_mt=Decimal(qty), status="POSTED", entered_by="TEST",
            ))
        for name,cls,qty in [("MCL-E","EICHER","35.92"),
                             ("MCL-B","BHARAT BENZ","39.25")]:
            db.add(SiteWeightFactor(
                factor_id=name,site_id="KOCP",
                factor_type="COAL_AVG_MT_PER_TRIP",
                factor_unit="MT/TRIP",factor_value=Decimal(qty),
                effective_from=DAY,effective_to=END,
                destination_location_id="KN5",material_id="COAL",
                vehicle_class=cls,source_org="MCL_MONTHLY",
                reference_no="MCL-2026-11",status="APPROVED",entered_by="TEST",
            ))
        db.commit()
        result=month_end_factor_reconciliation(
            db,site_id="KOCP",material_id="COAL",from_date=DAY,
            to_date=END,is_ob=False
        )
        assert result["basis"]=="MCL_MONTHLY_AVERAGE"
        assert result["trips"]==2
        assert Decimal(result["total"])==Decimal("75.170")
        assert {x["vehicleClass"] for x in result["rules"]}=={"EICHER","BHARAT BENZ"}
        assert db.get(SiteTrip,"TRIP-E1").quantity_mt==Decimal("33.440")
        # A missing certified factor blocks billing instead of guessing.
        final=db.get(SiteWeightFactor,"MCL-B")
        final.status="REJECTED"
        db.commit()
        with pytest.raises(HTTPException) as exc:
            month_end_factor_reconciliation(
                db,site_id="KOCP",material_id="COAL",from_date=DAY,
                to_date=END,is_ob=False,
            )
        assert exc.value.status_code==409
    engine.dispose()


def test_copy_search_and_mcl_final_category_interfaces_present():
    ui=(ROOT/"app/static/simple_field_v1.js").read_text("utf-8")
    mcl=(ROOT/"app/static/kocp_pointwise.js").read_text("utf-8")
    masters=(ROOT/"app/static/kocp_masters_compact.js").read_text("utf-8")
    fuel_api=(ROOT/"app/routers/site_ops.py").read_text("utf-8")
    assert "copyKocpTripRow(index)" in ui
    assert "GP is deliberately NOT copied" in ui
    assert "koTripSearch" in ui and "koHsdSavedSearch" in ui
    assert "kocpHsdSearch" in ui and "koHsdEntrySearch" in ui
    assert "byEquipmentCategory" in fuel_api
    assert "categorySummary" in fuel_api
    assert "MCL_MONTHLY" in mcl and "DAILY_REPORT" in mcl
    assert "koFactorClassesFromEquipment" in mcl
    assert "L150H is a Loader" in masters
    assert "return '<div class=\"kcm-form\"" in masters
