from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "app" / "routers" / "webapp.py"
UI = ROOT / "app" / "static" / "tiom_phase1.js"


def test_submitted_edit_requires_server_side_key_and_reason():
    api = API.read_text("utf-8")
    for term in (
        "TIOM_MIS_EDIT_KEY_CATEGORY",
        "def _require_tiom_mis_edit_key",
        "def save_tiom_mis_edit_key",
        "def verify_tiom_mis_edit_key",
        "_require_tiom_mis_edit_key(db,p.get('editKey'))",
        "editReason",
        "TIOM_MIS_EDIT_SUBMITTED",
        "before_snapshot=_tiom_mis_edit_snapshot",
        "after_snapshot=_tiom_mis_edit_snapshot",
        "report.approved_by=user.login_id",
        "report.approved_at=now_local()",
        "'Correction Audit'",
    ):
        assert term in api
    assert "if report and report.status=='VOID'" in api
    assert "if is_correction:" in api
    assert "open_shift(db,day,sh)" in api


def test_edit_key_is_hashed_not_stored_plaintext():
    api = API.read_text("utf-8")
    start = api.index("def save_tiom_mis_edit_key")
    end = api.index("def verify_tiom_mis_edit_key", start)
    block = api[start:end]
    assert "value=_tiom_mis_edit_key_hash(key)" in block
    assert "value=key" not in block
    assert "hmac.compare_digest" in api


def test_saved_report_ui_separates_view_and_key_edit():
    ui = UI.read_text("utf-8")
    for term in (
        "Edit (Key)",
        "Set Edit Key",
        'type="password"',
        "Edit Reason",
        "Save Corrected Version",
        "verifyTiomMisEditKey",
        "saveTiomMisEditKey",
        "AUTHORIZED CORRECTION MODE",
        "Submitted reports are read-only unless unlocked with the Edit Key.",
    ):
        assert term in ui
    assert "T.misEditKey=key" in ui
    assert "localStorage.setItem('misEditKey'" not in ui
    assert "sessionStorage.setItem('misEditKey'" not in ui


def test_historical_owned_wb_links_are_preserved_but_not_broadened():
    api = API.read_text("utf-8")
    assert "correction_wb_keys" in api
    assert "missing_owned=correction_wb_keys-set(wbmap)" in api
    assert "it was not already linked to this report" in api


def test_submitted_correction_does_not_auto_create_new_machine_assignment():
    api = API.read_text("utf-8")
    assert "if is_correction:" in api
    assert "corrected source / loader assignment is not in Machine Setup" in api
