"""Dashboard report export must be presentation-first and retain source safeguards."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "app/static/workspace.js").read_text(encoding="utf-8")
INDEX = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
EXPORT = (ROOT / "app/static/tiom_dashboard_presentation_export.js").read_text(encoding="utf-8")


def test_presentation_report_is_primary_and_raw_csv_remains_separate():
    assert 'onclick="dashboardPresentationReport(' in UI
    assert '>Download Excel Report</button>' in UI
    assert 'onclick="dashboardExcel()"' in UI
    assert 'dashboard-advanced-export' in UI
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


def test_all_additional_kpi_groups_are_present_and_keep_correct_sources():
    for heading in (
        "Production & recovery KPIs",
        "Haulage productivity & WB reconciliation",
        "HSD & equipment utilization",
        "Drilling performance",
        "Maintenance & month-to-date",
    ):
        assert heading in EXPORT
    for field in (
        "screenFinesMt", "screen518Mt", "crusherFeedMt", "crusherFreshOutputMt",
        "finalRecoveryPct", "crusherRecoveryPct", "balanceMt", "haulAvgLeadKm",
        "tripKmPerHour", "tonKmPerHour", "avgCycleTime", "avgLoadingTime",
        "matchRate", "misWbLinkedTrips", "matched", "wbUnmatched",
        "fuelPerTrip", "runningExcavators", "equipmentUtilization",
        "drillHoles", "drillMeterage", "drillMeterPerHour",
        "drillHsdLitres", "drillBreakdownHours",
        "activeEvents", "periodDowntimeHours", "avgDaily",
    ):
        assert field in EXPORT
    assert "hsdPerFinalTon" in EXPORT
    assert "allocationPending" in EXPORT
    assert "report-kpi-grid" in EXPORT


def test_report_renders_extra_kpis_and_protects_missing_allocation():
    import json
    import shutil
    import subprocess

    if not shutil.which("node"):
        import pytest
        pytest.skip("Node is needed to exercise the generated browser HTML")

    js = r"""
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[1], 'utf8');
let html = '', downloadCount = 0;
const d = {
  fromDate:'2026-11-02',toDate:'2026-11-02',shift:'B',
  materialFilter:'<img src=x onerror=alert(1)>',
  kpis:{wbTrips:794,wbTonnes:33241.62,wbUnmatched:41,haulLeadMissingTrips:20,
    haulAvgLeadKm:2.541,tripsPerHour:18.24,matchRate:87.75,hsdLitres:3600,
    workingEquipment:30,runningLoaders:4,runningExcavators:3,runningTippers:20,
    drillHoles:18,drillMeterage:150,drillHsdLitres:300,drillMeterPerHour:12.5},
  production:{romInputMt:13000,finalProductionMt:11000,finalRecoveryPct:84.615,
    crusherRecoveryPct:79.1,screenFinesMt:3200,screen518Mt:900,crusherFeedMt:7900},
  monthly:{actual:110000,avgDaily:3500},
  materials:[],routes:[],shiftComparison:[]
};
const S = {dashboard:d};
const document = {body:{appendChild(){}},createElement(){return {style:{},click(){downloadCount++;},remove(){}}}};
const URL = {createObjectURL(b){html=b.parts.join('');return 'blob:ok';},revokeObjectURL(){}};
class Blob {constructor(parts){this.parts=parts;}}
const window = {open(){return null;}};
vm.runInNewContext(src, {window,S,document,URL,Blob,setTimeout(){},toast(){}});
window.dashboardPresentationReport('download');
function assert(condition, message){if(!condition) throw Error(message);}
assert(downloadCount === 1, 'report download was not fired');
assert(html.startsWith('<!doctype html>'), 'report is not an HTML document');
assert(html.includes('Production &amp; recovery KPIs'), 'production KPI group missing');
assert(html.includes('Haulage productivity &amp; WB reconciliation'), 'haulage KPI group missing');
assert(html.includes('HSD &amp; equipment utilization'), 'HSD KPI group missing');
assert(html.includes('Drilling performance'), 'drilling KPI group missing');
assert(html.includes('Maintenance &amp; month-to-date'), 'monthly KPI group missing');
assert(html.includes('2.541 km'), 'average lead is missing');
assert(html.includes('87.8%'), 'match rate is missing or not rounded to dashboard precision');
assert(html.includes('150.00 m'), 'drill meterage is missing');
assert(html.includes('2.000 L/m'), 'drill HSD intensity is wrong');
assert(html.includes('1,10,000.00 t'), 'Indian-formatted MTD output is wrong');
assert(html.includes('&lt;img src=x onerror=alert(1)&gt;'), 'filter label was not escaped');
d.production.allocationPending = true;
d.production.finalProductionMt = null;
window.dashboardPresentationReport('download');
assert(html.includes('Final recovery</span><strong>Pending allocation'), 'pending recovery was fabricated');
assert(html.includes('HSD / fresh final t</span><strong>Not available'), 'unverified fuel intensity was fabricated');
d.kpis.drillMeterage = 0;
window.dashboardPresentationReport('download');
assert(html.includes('Drill HSD / metre</span><strong>Not available'), 'division by zero is not guarded');
console.log('dashboard report KPI checks passed');
"""
    check = subprocess.run(
        ["node", "-e", js, str(ROOT / "app/static/tiom_dashboard_presentation_export.js")],
        capture_output=True, text=True, timeout=15,
    )
    assert check.returncode == 0, check.stdout + "\n" + check.stderr
    assert "checks passed" in check.stdout
