"""Regression tests: management XLSX download and management-only cross-site switch."""
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from app.routers.tiom_dashboard_export import make_workbook, metric_groups

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app/static"


def dashboard_data(pending=False):
    return {
        "fromDate": "2026-11-02", "toDate": "2026-11-02", "shift": "B",
        "materialFilter": "ROM", "sourceFilter": "Main", "destinationFilter": "",
        "vehicleFilter": "",
        "kpis": {"wbTrips": 794, "wbTonnes": 33241.62, "avgPayload": 41.87,
                 "hsdLitres": 100, "drillMeterage": 50, "drillHsdLitres": 120,
                 "wbUnmatched": 10},
        "production": {"romInputMt": 9401.02, "screenDirectMt": 2100,
                       "crusherGrossOutputMt": 4500, "finalProductionMt": None if pending else 6100,
                       "finalRecoveryPct": None if pending else 64.89,
                       "allocationPending": pending},
        "monthly": {"actual": 6200, "avgDaily": 3100},
        "materials": [{"label": "ROM", "trips": 230, "tonnes": 9401.02, "pct": 28.28},
                      {"label": "=2+2", "trips": 1, "tonnes": 20}],
        "productionMaterials": [{"label": "ROM", "trips": 230, "tonnes": 9401.02,
                                 "monthTonnes": 19600, "avgPayload": 40.87, "pct": 100, "kind": "INPUT"}],
        "plantPerformance": [{"plant": "Screen", "freshFeedMt": 9401.02, "outputMt": 6100,
                              "runningHours": 8, "tph": 1175.12}],
        "shiftComparison": [{"shift": "B", "trips": 230, "tonnes": 9401.02, "fuel": 100}],
        "haulagePerformance": [{"source": "Main", "destination": "Screen", "trips": 230,
                                "leadStatus": "MISSING"}],
        "fuelByEquipment": [{"machine": "EX-01", "type": "EXCAVATOR", "litres": 100}],
        "drilling": {"rows": [{"label": "Drill 1", "holes": 8, "totalMeterage": 50}]},
        "exceptions": [{"severity": "WARN", "label": "Lead Missing", "value": 10}],
        "notes": ["Fresh ROM is the base."],
    }


def test_excel_report_is_styled_multi_sheet_and_has_48_kpi_cards():
    data = dashboard_data()
    groups = metric_groups(data)
    assert [len(items) for _, items in groups] == [8, 8, 12, 8, 6, 6]
    wb, count = make_workbook(data)
    assert count == 48
    assert wb.sheetnames == [
        "KPI Dashboard", "Production Materials", "Plant Performance",
        "Shift Comparison", "WB Material Audit", "Haulage Routes",
        "Fuel & Equipment", "Drilling Details", "Data Quality",
    ]
    summary = wb["KPI Dashboard"]
    assert summary["A1"].value.startswith("NMTPL")
    assert "2026-11-02" in summary["A3"].value
    assert "Shift B" in summary["A3"].value
    assert summary["A6"].value == "Fresh ROM"
    assert summary["A7"].value == 9401.02
    assert summary["A7"].number_format.endswith('" t"')
    assert summary["A7"].font.bold
    assert wb["Production Materials"]["A6"].value == "ROM"
    assert wb["Plant Performance"]["A6"].value == "Screen"
    assert wb["WB Material Audit"]["C6"].value == 9401.02
    assert len(wb["WB Material Audit"]._charts) == 1
    assert wb["KPI Dashboard"].sheet_view.showGridLines is False
    assert wb["KPI Dashboard"].page_setup.orientation == "landscape"
    assert wb["Data Quality"]["B6"].value == "Lead Missing"
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    loaded = load_workbook(stream, data_only=False)
    assert loaded["KPI Dashboard"]["A7"].value == 9401.02
    # Untrusted source strings must be text and never become formulas.
    assert loaded["WB Material Audit"]["A7"].data_type != "f"


def test_allocation_pending_and_denominator_safety():
    data = dashboard_data(pending=True)
    data["kpis"]["drillMeterage"] = 0
    wb, _ = make_workbook(data)
    found = [(label, value) for _, items in metric_groups(data) for label, value, *_ in items]
    values = dict(found)
    assert values["Final fresh production"] == "Pending allocation"
    assert values["Final recovery"] == "Pending allocation"
    assert values["Production balance"] == "Pending allocation"
    assert values["HSD / final tonne"] is None
    assert values["Drill HSD / metre"] is None
    texts = [c.value for row in wb["KPI Dashboard"] for c in row if isinstance(c.value, str)]
    assert "Pending allocation" in texts
    assert "Not available" in texts


def test_excel_download_toolbar_and_site_switchers_are_connected():
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    dashboard_ui = (STATIC / "workspace.js").read_text(encoding="utf-8")
    exporter = (STATIC / "tiom_dashboard_presentation_export.js").read_text(encoding="utf-8")
    tiom_shell = (STATIC / "webapp.js").read_text(encoding="utf-8")
    site = (STATIC / "site.js").read_text(encoding="utf-8")
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "dashboardExcel()" in dashboard_ui
    assert "Download Excel Report" in dashboard_ui
    assert "dashboard-advanced-export" in dashboard_ui
    assert "Raw CSV" in dashboard_ui
    assert "report.xlsx" in exporter
    assert "X-NMTPL-Request" in exporter
    for key in ("fromDate", "toDate", "shift", "materialFilter",
                "sourceFilter", "destinationFilter", "vehicleFilter"):
        assert key in exporter
    assert "app.include_router(tiom_dashboard_export.router)" in main
    assert 'id="tiomSiteJump"' in index
    assert "sitePicker.hidden=!boot.user.isManagement" in tiom_shell
    assert "if(!S.boot?.user?.isManagement)return" in tiom_shell
    assert "KOCP:'/site/KOCP'" in tiom_shell
    assert "SOCP:'/site/SOCP'" in tiom_shell
    assert "b.user.isManagement||" in site
    assert "chosen==='TIOM'?'/tiom'" in site
    assert "chosen==='CENTRAL'?'/central-control'" in site
