"""Regression: Despatch MTD report must locate date-specific missing categories."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.routers.tiom_despatch import _month_mapping_issue_rows

ROOT = Path(__file__).resolve().parents[1]


def trip(day, permit, buyer="", destination="", material="", tonnes="33.500"):
    return SimpleNamespace(
        report_date=date.fromisoformat(day),
        permit_no=permit,
        buyer=buyer,
        destination=destination,
        material_grade=material,
        net_mt=Decimal(tonnes),
    )


def test_missing_november_first_is_visible_when_second_is_complete():
    groups = [
        ("L102605571", 173), ("L102604967", 41),
        ("L102604966", 30), ("L102605612", 13),
        ("L102601592", 3), ("L102604962", 1),
    ]
    rows = [
        trip("2026-11-01", permit)
        for permit, count in groups for _ in range(count)
    ]
    rows += [trip("2026-11-02", "L102605571", "Self", "Dabuna", "C.Fines(60-62)")
             for _ in range(8)]
    rows += [trip("2026-11-02", "L102605612", "Self", "Dabuna", "C.Fines(60-62)")
             for _ in range(179)]
    issues = _month_mapping_issue_rows(rows, {})
    assert len(issues) == 6
    assert sum(item["missingTrips"] for item in issues) == 261
    assert {item["reportDate"] for item in issues} == {"2026-11-01"}
    assert {item["tripCount"] for item in issues} == {173, 41, 30, 13, 3, 1}
    repeated = next(x for x in issues if x["permitNo"] == "L102605571")
    assert repeated["buyer"] == ""
    assert repeated["samePermitSource"] == {
        "reportDate": "2026-11-02",
        "buyer": "Self", "destination": "Dabuna", "material": "C.Fines(60-62)",
    }
    assert next(x for x in issues if x["permitNo"] == "L102604962")["samePermitSource"] is None


def test_confirmed_permit_is_projected_for_reports_without_mutating_epass():
    original = trip("2026-11-01", "L102605571")
    saved = SimpleNamespace(buyer="Self", destination="Dabuna", material="C.Fines(60-62)",
                            grade_percent="", permit_qty=None, balance_mt=None)
    issues = _month_mapping_issue_rows([original], {(original.report_date, "L102605571"): saved})
    assert issues == []
    assert original.buyer == ""
    assert original.material_grade == ""


def test_invalid_material_grade_is_exposed_with_date_and_permit():
    original = trip("2026-11-01", "L102605571")
    saved = SimpleNamespace(buyer="Self", destination="Dabuna", material="SCREENED FINES",
                            grade_percent="", permit_qty=None, balance_mt=None)
    issues = _month_mapping_issue_rows([original], {(original.report_date, "L102605571"): saved})
    assert len(issues) == 1
    assert issues[0]["missingTrips"] == 1
    assert issues[0]["permitNo"] == "L102605571"
    assert issues[0]["reason"]


def test_five_reports_has_direct_mtd_correction_form_and_save_action():
    html=(ROOT/"app/static/index.html").read_text("utf-8")
    js=(ROOT/"app/static/tiom_despatch.js").read_text("utf-8")
    assert "mtd-inline-fix-20261103" in html
    assert "mapping-issues?to_date=" in js
    assert "issues.totalMissingTrips" in js
    assert "tiomDDSaveMappingIssue" in js
    assert "tiomDDUseSamePermitSource" in js
    assert "api('permit-entry-one'" in js
    assert "Original Gmail E-Pass weights" in js
