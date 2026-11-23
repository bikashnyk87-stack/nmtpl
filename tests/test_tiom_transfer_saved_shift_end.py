"""Regression: a saved A-shift 06–14 assignment may transfer at 10:00."""
import ast
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
API=(ROOT/"app/routers/webapp.py").read_text("utf-8")
UI=(ROOT/"app/static/tiom_phase1.js").read_text("utf-8")
TZ=ZoneInfo("Asia/Kolkata")


def _transferable_end():
    module=ast.parse(API)
    node=next(n for n in module.body if isinstance(n,ast.FunctionDef)
              and n.name=="_tiom_transferable_end")
    context={"TZ":TZ}
    exec(compile(ast.Module(body=[node],type_ignores=[]),"webapp.py","exec"),context)
    return context[node.name]


def test_scheduled_shift_end_is_eligible_but_earlier_closed_transfer_is_not():
    allowed=_transferable_end()
    shift_end=datetime(2026,11,22,14,0,tzinfo=TZ)
    assert allowed(None,shift_end)
    assert allowed(datetime(2026,11,22,14,0,tzinfo=TZ),shift_end)
    assert allowed(datetime(2026,11,22,14,0),shift_end)
    assert not allowed(datetime(2026,11,22,10,0,tzinfo=TZ),shift_end)
    assert not allowed(datetime(2026,11,22,15,0,tzinfo=TZ),shift_end)
    # Overnight C on 22 Nov closes on 23 Nov at 06:00 IST.
    c_end=datetime(2026,11,23,6,0,tzinfo=TZ)
    assert allowed(datetime(2026,11,23,6,0,tzinfo=TZ),c_end)
    assert not allowed(datetime(2026,11,23,4,0,tzinfo=TZ),c_end)


def test_transfer_resolves_date_effective_shift_and_preserves_overlap_guards():
    assert "def _tiom_transfer_shift_bounds(day, shift)" in API
    assert "from app.services.tiom_shift_schedule import times_for_day" in API
    section=API.split("def transfer_tiom_source_deployment(",1)[1].split(
        "\ndef _tiom_source_correction_reason",1)[0]
    assert "_tiom_transfer_shift_bounds(day, sh)" in section
    assert "if not _tiom_transferable_end(origin.to_at, shift_end):" in section
    assert "shift_start<end_at<=start_at<shift_end" in section
    assert "_tiom_deployment_overlap(start_at,None,other.from_at,other.to_at)" in section
    assert "origin.to_at=end_at" in section
    assert "from_at=start_at,to_at=None" in section
    assert "'TIOM_SOURCE_TRANSFER'" in section
    assert "later_trip" in section


def test_api_returns_saved_options_and_respects_current_date_and_shift():
    assert "def get_tiom_transfer_options(db, user, p):" in API
    part=API.split("def get_tiom_transfer_options(",1)[1].split(
        "\ndef transfer_tiom_source_deployment(",1)[0]
    assert "_tiom_context(db, user, p)" in part
    assert "_tiom_source_deployments(db, day, sh)" in part
    assert "_tiom_transferable_end(r.to_at, shift_end)" in part
    assert "'savedCount': len(all_rows)" in part
    assert "if method == 'getTiomTransferOptions':" in API
    assert "'getTiomTransferOptions'" in API.split("read_methods =",1)[1].split("\n",1)[0]
    assert "getTiomTransferOptions({date,shift})" in UI
    assert "panel.dataset.deploymentId=r.deploymentId" in UI
    assert "if(r.toTime){toast('This location is already finished." not in UI
