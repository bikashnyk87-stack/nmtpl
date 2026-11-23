"""TIOM HMR grid must be compact without losing audited transfer boundaries."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
UI=(ROOT/"app/static/tiom_phase1.js").read_text(encoding="utf-8")
CSS=(ROOT/"app/static/tiom_phase1.css").read_text(encoding="utf-8")
PAGE=(ROOT/"app/static/index.html").read_text(encoding="utf-8")
API=(ROOT/"app/routers/webapp.py").read_text(encoding="utf-8")


def test_hmr_grid_has_only_ten_visible_columns():
    marker='<table class="tiom-entry-table tiom-deploy-table"><thead><tr>'
    head=UI.split(marker,1)[1].split("</tr>",1)[0]
    assert re.findall(r"<th>(.*?)</th>",head)==[
        "#","Source / RL","Equipment / Machine","Operator Name",
        "Activity","HMR Open","HMR Close","Run","Reset","Note"
    ]
    fragment=UI.split("function renderDeploymentRows(existing)",1)[1].split("window.addDeploymentRow",1)[0]
    row=fragment.split("h+=`<tr>",1)[1].split("</tr>`",1)[0]
    assert len(re.findall(r"<td(?: |>)",row))==10
    assert 'id="td_from_${i}" type="time"' not in row
    assert 'id="td_to_${i}" type="time"' not in row
    assert 'type="hidden" id="td_from_${i}" value="${safe(r.fromTime||\'\')}"' in row
    assert 'type="hidden" id="td_to_${i}" value="${safe(r.toTime||\'\')}"' in row


def test_transfer_still_uses_saved_boundaries_and_audited_explicit_changeover():
    assert "fromTime:v('td_from_'+i),toTime:v('td_to_'+i)" in UI
    assert "getTiomTransferOptions({date,shift})" in UI
    assert "(result.rows||[]).filter(r=>r.deploymentId&&r.machineId&&r.sourceLocationId)" in UI
    assert 'id="tm_transfer_end"' in UI
    assert 'id="tm_transfer_start"' in UI
    assert "transferTiomSourceDeployment({" in UI
    assert "endTime,startTime,notes:v('tm_transfer_notes')" in UI
    assert "def transfer_tiom_source_deployment" in API
    assert "origin.to_at=end_at" in API
    assert "from_at=start_at,to_at=None" in API
    assert "'TIOM_SOURCE_TRANSFER'" in API


def test_ten_column_css_and_contained_form_controls():
    assert "table-layout:fixed" in CSS
    assert ".tiom-deploy-table td:nth-child(10)" in CSS
    assert ".tiom-deploy-table td:nth-child(12)" not in CSS
    assert "#tm_dep_panel .tiom-deploy-table tbody td" in CSS
    assert "max-width:100%!important;min-width:0!important" in CSS
    assert "#tm_transfer_panel .tm-transfer-fields" in CSS
    assert "#tm_transfer_panel .tm-transfer-picker select" in CSS


def test_live_asset_urls_refer_to_updated_scripts():
    assert "/static/tiom_phase1.js?v=tiom-transfer-live-shiftend-20261123" in PAGE
    assert "/static/tiom_phase1.css?v=tiom-hmr-ten-cols-20261123" in PAGE
