"""KOCP material/point/route factor selection and report contract guards."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.kocp_factor_rules import choose_point_factor


DAY = date(2026, 11, 2)
ROOT = Path(__file__).parents[1]


def factor(fid, **overrides):
    base = dict(
        factor_id=fid, status="APPROVED",
        effective_from=date(2026, 11, 1), effective_to=None,
        operating_date=None, shift=None,
        destination_location_id="KOCP:DUMP", route_id=None,
        material_id="KOCP:SOFT_OB", vehicle_class=None,
        factor_value=Decimal("15.200000"),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def pick(rows, **kwargs):
    base=dict(
        operating_day=DAY, shift="A", destination_id="KOCP:DUMP",
        route_id="OB-ROUTE-1", material_id="KOCP:SOFT_OB",
        vehicle_type="VOLVO", vehicle_group="TRIPPER",
    )
    base.update(kwargs)
    return choose_point_factor(rows, **base)


def test_point_route_overrides_destination_general_and_shift():
    general=factor("GENERAL", material_id=None, factor_value=Decimal("14.0"))
    dest=factor("POINT", factor_value=Decimal("15.2"))
    route=factor("ROUTE", route_id="OB-ROUTE-1", factor_value=Decimal("16.8"))
    other=factor("WRONG", destination_location_id="KOCP:OTHER", factor_value=Decimal("99"))
    assert pick([general,dest,route,other]).factor_id=="ROUTE"
    assert pick([general,dest,route], route_id="OB-ROUTE-2").factor_id=="POINT"


def test_factor_shift_material_class_and_date_scope():
    global_one=factor("POINT")
    exact=factor("SHIFT", shift="A", vehicle_class="VOLVO", factor_value=Decimal("18"))
    assert pick([global_one,exact]).factor_id=="SHIFT"
    assert pick([global_one,exact], shift="B").factor_id=="POINT"
    assert pick([global_one,exact], vehicle_type="BHARAT BENZ").factor_id=="POINT"
    with pytest.raises(HTTPException):
        pick([global_one,exact], material_id="KOCP:HARD_OB")


def test_missing_and_legacy_global_rules_fail_closed():
    legacy=factor("GLOBAL", destination_location_id=None, material_id=None)
    wrong_dest=factor("OTHER", destination_location_id="KOCP:ANOTHER")
    with pytest.raises(HTTPException) as err:
        pick([legacy,wrong_dest])
    assert err.value.status_code==409
    assert "unloading point" in err.value.detail


def test_equal_specificity_is_blocked_instead_of_guessing():
    with pytest.raises(HTTPException) as err:
        pick([factor("ONE"),factor("TWO",factor_value=Decimal("99"))])
    assert err.value.status_code==409
    assert "Multiple" in err.value.detail


def test_expired_unapproved_and_other_date_rules_ignored():
    good=factor("CURRENT")
    expired=factor("EXPIRED",effective_to=date(2026,10,31))
    draft=factor("DRAFT",status="DRAFT")
    future=factor("FUTURE",effective_from=date(2026,11,3))
    day_other=factor("OTHER-DATE",operating_date=date(2026,11,1))
    assert pick([expired,draft,future,day_other,good]).factor_id=="CURRENT"


def test_rule_ui_and_report_are_wired_with_separate_units():
    source=(ROOT/"app/static/kocp_pointwise.js").read_text("utf-8")
    html=(ROOT/"app/static/site.html").read_text("utf-8")
    core=(ROOT/"app/routers/site_ops.py").read_text("utf-8")
    assert "kocp_pointwise.js" in html
    assert "COAL_AVG_MT_PER_TRIP" in source and "OB_CUM_PER_TRIP" in source
    assert "destinationLocationId" in source and "routeId" in source
    assert "renderKocpPointReport" in source
    assert '"/KOCP/reports/point-wise"' in core
    assert "SiteTrip.status == \"POSTED\"" in core
    assert "weightedAverage" in core
