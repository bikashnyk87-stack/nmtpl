"""One MIS category entry must serve all consistent dates of a continuing permit."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.routers.tiom_despatch import _report_verified_amns, _month_mapping_issue_rows


class FakeDB:
    def __init__(self, confirmations):
        self.confirmations = confirmations

    def scalars(self, statement):
        return iter(self.confirmations)


def trip(day, permit, buyer="", destination="", material="", consignee="071813056432/AMNS"):
    return SimpleNamespace(
        report_date=date.fromisoformat(day), permit_no=permit,
        buyer=buyer, destination=destination, material_grade=material,
        consignee=consignee, net_mt=Decimal("35.000"),
        status="ACTIVE", epass_no="TEST",
    )


def verified(day, permit, buyer, destination, material, percent):
    return SimpleNamespace(
        report_date=date.fromisoformat(day), permit_no=permit,
        buyer=buyer, destination=destination, material=material,
        grade_percent=percent, permit_qty=None, balance_mt=None,
    )


def test_four_confirmed_mis_permits_cover_219_prior_day_epasses_without_reentry():
    groups = [
        ("L102605571", 173), ("L102604967", 41),
        ("L102604966", 30), ("L102605612", 13),
        ("L102601592", 3), ("L102604962", 1),
    ]
    rows = [
        trip("2026-11-01", permit)
        for permit, count in groups for _ in range(count)
    ]
    original_rows = list(rows)
    confirmations = [
        verified("2026-11-02", "L102605571", "Self", "Dabuna", "C.Fines(60-62)", "60.65"),
        verified("2026-11-02", "L102604966", "PH ASSOCIATES PRIVATE LIMITED", "Palaspanga", "5-18mm(60-62)", "60.78"),
        verified("2026-11-02", "L102605612", "Self", "Dabuna", "C.Fines(60-62)", "60.78"),
        verified("2026-11-02", "L102601592", "PH ASSOCIATES PRIVATE LIMITED", "Kuarmunda(SNG)", "5-18mm(60-62)", "60.78"),
    ]
    rows += [
        trip("2026-11-02", r.permit_no, r.buyer, r.destination, r.material)
        for r in confirmations
    ]
    db = FakeDB(confirmations)
    projected = _report_verified_amns(db, rows)
    assert len(projected) == len(rows)
    inherited = [x for x in projected if getattr(x, "inherited_from_mis", False)]
    assert len(inherited) == 219
    assert {x.permit_no for x in inherited} == {
        "L102605571", "L102604966", "L102605612", "L102601592",
    }
    assert all(x.mis_source_date == date(2026, 11, 2) for x in inherited)
    assert all(x.buyer == "" for x in original_rows)  # No E-Pass mutation
    saved_by_date = {(x.report_date, x.permit_no): x for x in confirmations}
    issues = _month_mapping_issue_rows(projected, saved_by_date)
    assert len(issues) == 2
    assert sum(x["missingTrips"] for x in issues) == 42
    assert {x["permitNo"] for x in issues} == {"L102604967", "L102604962"}


def test_confirmed_mis_permit_quantity_fills_only_missing_report_values():
    saved=verified("2026-11-02","L102605612","Self","Dabuna",
                   "C.Fines(60-62)","60.65")
    saved.permit_qty=Decimal("6066.840")
    early=trip("2026-11-01","L102605612")
    same_day=trip("2026-11-02","L102605612")
    explicit=trip("2026-11-02","L102605612")
    explicit.permit_qty=Decimal("6050.000")
    projected=_report_verified_amns(FakeDB([saved]),[early,same_day,explicit])
    assert projected[0].permit_qty==Decimal("6066.840")
    assert projected[1].permit_qty==Decimal("6066.840")
    assert projected[2].permit_qty==Decimal("6050.000")
    assert not hasattr(early,"permit_qty")  # source unchanged


def test_mismatched_consignee_refuses_inherited_category():
    confirmed = verified("2026-11-02", "L102605571", "Self", "Dabuna", "C.Fines(60-62)", "60.65")
    rows = [
        trip("2026-11-01", "L102605571", consignee="OTHER PARTY"),
        trip("2026-11-02", "L102605571"),
    ]
    projected = _report_verified_amns(FakeDB([confirmed]), rows)
    assert projected[0].buyer == ""
    assert not getattr(projected[0], "inherited_from_mis", False)


def test_conflicting_confirmed_mis_categories_require_manual_mis_review():
    a=verified("2026-11-02", "L102605571", "Self", "Dabuna", "C.Fines(60-62)", "60.65")
    b=verified("2026-11-03", "L102605571", "Self", "Dabuna", "S.Fines(60-62)", "60.65")
    rows=[
        trip("2026-11-01", "L102605571"),
        trip("2026-11-02", "L102605571"),
        trip("2026-11-03", "L102605571"),
    ]
    projected=_report_verified_amns(FakeDB([a,b]),rows)
    assert projected[0].buyer == ""
    assert getattr(projected[0], "inherited_from_mis", False) is False


def test_inherited_fields_never_override_inconsistent_existing_source():
    confirmed=verified("2026-11-02", "L102605571", "Self", "Dabuna", "C.Fines(60-62)", "60.65")
    rows=[
        trip("2026-11-01", "L102605571", buyer="PH ASSOCIATES PRIVATE LIMITED"),
        trip("2026-11-02", "L102605571"),
    ]
    projected=_report_verified_amns(FakeDB([confirmed]),rows)
    assert projected[0].buyer == "PH ASSOCIATES PRIVATE LIMITED"
    assert getattr(projected[0], "inherited_from_mis", False) is False
