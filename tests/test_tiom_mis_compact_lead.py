"""Static regression for the compact TIOM MIS lead preview (no payroll/WB changes)."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_lead_preview_one_line_without_dropping_validation():
    js=(ROOT/"app/static/tiom_phase1.js").read_text("utf-8")
    block=js[js.index("const compactLeadStatus="):js.index("window.tripSourceChanged=")]
    assert "'Select destination':'—'" in block
    assert "'RL missing in Source Master':'No RL'" in block
    assert "'Lead Master conflict':'Conflict'" in block
    assert "'Lead not configured':'No lead'" in block
    assert "'Route not configured':'No route'" in block
    assert "el.dataset.lead=out.leadKm==null?'':String(out.leadKm)" in block
    assert "el.title=" in block and "out.status" in block
    assert "n(out.leadKm,3)+' km'" in block


def test_compact_trip_table_only_and_cache_refresh():
    css=(ROOT/"app/static/tiom_phase1.css").read_text("utf-8")
    html=(ROOT/"app/static/index.html").read_text("utf-8")
    assert "#tm_trip_panel .erp-trip-table tbody tr{height:27px}" in css
    assert "#tm_trip_panel .erp-trip-table td.qty-preview{white-space:nowrap!important" in css
    assert "#tm_trip_panel .erp-trip-table tbody td{padding:1px 3px!important" in css
    assert "font-size:9.5px!important;line-height:1.15!important" in css
    assert "#tm_trip_panel .erp-trip-table thead th{padding:3px 4px!important;font-size:9px!important" in css
    assert "/static/tiom_phase1.js?v=tiom-drilling-static-hmr-20261125" in html
    assert "/static/tiom_phase1.css?v=tiom-drilling-fit-entry-20261125" in html
