"""Regression tests for shifting TIOM equipment between working locations."""
import ast
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "app" / "routers" / "webapp.py"
UI = ROOT / "app" / "static" / "tiom_phase1.js"


def overlap(a_from, a_to, b_from, b_to):
    """Exercise the actual production overlap helper in isolation."""
    module = ast.parse(API.read_text(encoding="utf-8"))
    func = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_tiom_deployment_overlap"
    )
    namespace = {}
    exec(compile(ast.Module(body=[func], type_ignores=[]), str(API), "exec"), namespace)
    return namespace["_tiom_deployment_overlap"](a_from, a_to, b_from, b_to)


def test_closed_location_can_be_followed_by_new_location():
    day = datetime(2026, 10, 15)
    finish = day.replace(hour=10)
    start = day.replace(hour=10, minute=20)
    assert not overlap(None, finish, start, None)
    assert not overlap(start, None, None, finish)
    assert not overlap(None, finish, finish, None)


def test_simultaneous_or_open_end_assignments_are_blocked():
    day = datetime(2026, 10, 15)
    old_end = day.replace(hour=10)
    premature_start = day.replace(hour=9, minute=45)
    assert overlap(None, old_end, premature_start, None)
    assert overlap(None, None, day.replace(hour=11), None)
    assert overlap(day.replace(hour=9), day.replace(hour=12),
                   day.replace(hour=10), day.replace(hour=11))


def test_transfer_is_audited_and_uses_existing_row_id():
    api = API.read_text(encoding="utf-8")
    ui = UI.read_text(encoding="utf-8")
    for term in (
        "def transfer_tiom_source_deployment",
        "origin.to_at=end_at",
        "from_at=start_at,to_at=None",
        "'TIOM_SOURCE_TRANSFER'",
        "TiomSourceDeployment.deployment_id!=origin.deployment_id",
        "if machine_deployments:",
        "if dep_matches and loading",
        "existing_by_id={r.deployment_id:r",
        "if method == 'transferTiomSourceDeployment'",
    ):
        assert term in api, term
    for term in (
        "↪ Transfer Equipment",
        "openMachineTransfer",
        "chooseMachineTransfer",
        "startMachineTransfer",
        "confirmMachineTransfer",
        "transferTiomSourceDeployment({",
        "deploymentId:v('td_id_'+i)",
        "machinesForSource(sourceId,selected,loadingTime='')",
    ):
        assert term in ui, term


def test_transfer_button_is_visible_and_static_cache_is_busted():
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "tiom_phase1.css").read_text(encoding="utf-8")
    ui = UI.read_text(encoding="utf-8")
    assert 'onclick="openMachineTransfer()"' in ui
    assert "id=\"tm_transfer_panel\"" in ui
    assert "<th>Transfer</th>" not in ui
    assert "tm-transfer-fields" in ui
    assert "tiom_phase1.js?v=tiom-dpr-20261023-r1" in html
    assert "tiom_phase1.css?v=tiom-drilling-kpi-20261018-r1" in html
    assert ".tm-transfer-panel" in css
    assert "td:nth-child(12)" in css
