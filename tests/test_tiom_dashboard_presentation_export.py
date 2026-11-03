"""Dashboard report export must be presentation-first and retain source safeguards."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "app/static/workspace.js").read_text(encoding="utf-8")
INDEX = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
EXPORT = (ROOT / "app/static/tiom_dashboard_presentation_export.js").read_text(encoding="utf-8")


def test_presentation_report_is_primary_and_raw_csv_remains_separate():
    assert 'onclick="dashboardPresentationReport(' in UI
    assert '>Download Report</button>' in UI
    assert '>Raw CSV</button>' in UI
    assert 'onclick="dashboardPrint()"' in UI
    assert 'tiom_dashboard_presentation_export.js' in INDEX


def test_export_uses_live_filtered_dashboard_and_not_a_raw_kpi_dump():
    assert 'S.dashboard' in EXPORT
    for source in (
        'd.fromDate', 'd.toDate', 'd.shift', 'd.materialFilter',
        'd.sourceFilter', 'd.destinationFilter', 'd.vehicleFilter',
        'd.productionMaterials', 'd.plantPerformance', 'd.materials',
        'd.shiftComparison', 'd.routes',
    ):
        assert source in EXPORT
    for label in (
        'Production flow & allocation', 'Material production',
        'Plant feed vs output', 'Shift comparison',
        'WB routes & locations', 'Management notes & data coverage',
    ):
        assert label in EXPORT


def test_report_does_not_fabricate_final_production_or_lead():
    assert 'allocationPending' in EXPORT
    assert 'Final fresh production is not estimated' in EXPORT
    assert 'Unmapped source / destination' in EXPORT
    assert 'not the finished-product total' in EXPORT
    assert '@page{size:A4 landscape' in EXPORT
    assert "window.dashboardPrint = function ()" in EXPORT
