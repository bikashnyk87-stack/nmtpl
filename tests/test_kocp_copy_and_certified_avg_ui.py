"""KOCP production entry uses one copy action; monthly average entry belongs with certification."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_single_kocp_copy_down_toolbar_no_row_buttons():
    source = (ROOT / "app/static/simple_field_v1.js").read_text(encoding="utf-8")
    grid = source.split("function tripGridRows(", 1)[1].split("async function renderSimpleTrips(", 1)[0]
    entry = source.split("async function renderSimpleTrips(", 1)[1].split("function kocpTripCorrectionMarkup(", 1)[0]
    assert "copyKocpTripRow(${i})" not in grid
    assert 'onclick="copyKocpLastTripRow()"' in entry
    assert entry.count('onclick="copyKocpLastTripRow()"') == 1
    assert "function copyKocpLastTripRow()" in source
    assert "GP is deliberately NOT copied" in source
    assert "r.dataset.saved" in source
    assert "stVehicle" in source and "stGp" in source


def test_monthly_mcl_average_in_certified_screen_only():
    point = (ROOT / "app/static/kocp_pointwise.js").read_text(encoding="utf-8")
    survey = (ROOT / "app/static/site_ops.js").read_text(encoding="utf-8")
    assert "const final=options.final===true;" in point
    assert "final?'MCL_MONTHLY':'DAILY_REPORT'" in point
    assert "visibleRules=rules.filter" in point
    assert "if(final)return entry+register;" in point
    assert "renderKocpPointFactors({final:true})" in survey
    assert "independently certified total" in survey
    assert "MCL monthly" in survey


def test_daily_and_monthly_reconciliation_backends_remain_separate():
    factor = (ROOT / "app/services/kocp_factor_rules.py").read_text(encoding="utf-8")
    monthly = (ROOT / "app/services/kocp_monthly_billing.py").read_text(encoding="utf-8")
    billing = (ROOT / "app/routers/site_ops.py").read_text(encoding="utf-8")
    assert "allowed_sources: tuple[str, ...] = ('DAILY_REPORT', 'MCL')" in factor
    assert 'SiteWeightFactor.source_org == "MCL_MONTHLY"' in monthly
    assert '"MCL_MONTHLY_AVERAGE"' in billing
    assert "MCL survey quantity differs" in billing
