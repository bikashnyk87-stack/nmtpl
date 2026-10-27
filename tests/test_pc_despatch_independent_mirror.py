"""An independent Despatch PC mirror must not change existing WB sync state."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest


@pytest.fixture
def mirror(tmp_path, monkeypatch):
    # Use isolated PC-like dir, never the configured production PC location.
    root = tmp_path / "pc"
    root.mkdir()
    old = Path.cwd()
    monkeypatch.setenv("NMTPL_PC_PROJECT_ROOT", str(root))
    spec = importlib.util.spec_from_file_location(
        "pc_despatch_mirror_isolated",
        Path(__file__).parents[1] / "scripts" / "pc_despatch_mirror_standalone.py",
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(old)
    return module


def test_mirror_schema_only_despatch_tables(mirror):
    assert set(mirror.schema().tables) == set(mirror.TABLE_NAMES)
    tables = mirror.schema().tables
    assert "epass_no" in tables["tiom_despatch_trip"].c
    assert "report_date" in tables["tiom_despatch_trip"].c
    assert "net_mt" in tables["tiom_despatch_trip"].c
    assert "wb_movement" not in tables
    assert "sync_change_log" not in tables


def test_mirror_uses_original_pairing_and_prevents_unknown_host(mirror):
    mirror.CONFIG.parent.mkdir(parents=True, exist_ok=True)
    mirror.CONFIG.write_text(json.dumps({
        "base_url": "https://unauthorized.example.com",
        "token": "A"*48,
    }), encoding="utf-8")
    with pytest.raises(RuntimeError, match="unexpected URL"):
        mirror.get_config()
    mirror.CONFIG.write_text(json.dumps({
        "base_url": mirror.REMOTE,
        "token": "A"*48,
    }), encoding="utf-8")
    cfg, token = mirror.get_config()
    assert token == "A"*48
    assert cfg["base_url"] == mirror.REMOTE


def test_only_despatch_changed_records_are_applied(mirror, monkeypatch):
    records = []
    local = {}
    saved = {}
    monkeypatch.setattr(mirror, "check_schema", lambda: None)
    monkeypatch.setattr(mirror, "load_state", lambda: {})
    monkeypatch.setattr(mirror, "snapshot_all", lambda token, initial:
                        (100, {"tiom_despatch_trip": 2}))
    monkeypatch.setattr(mirror, "manifest", lambda token: {
        "tables": list(mirror.TABLE_NAMES),
        "watermark": 103,
        "despatchRowCounts": {n: 2 if n=="tiom_despatch_trip" else 0
                              for n in mirror.TABLE_NAMES},
    })
    monkeypatch.setattr(mirror, "atomic_write",
                        lambda path, obj: saved.update({"state": dict(obj)}))
    def fake_feed(cursor, token):
        assert cursor == 100
        return {"lastChangeId": 103, "hasMore": False, "changes": [
            {"table": "wb_movement", "operation": "U", "row": {"x": 4}},
            {"table": "tiom_despatch_trip", "operation": "U",
             "row": {"epass_no": "X", "net_mt": 10}},
        ]}
    monkeypatch.setattr(mirror, "change_feed", fake_feed)
    monkeypatch.setattr(mirror, "save_rows",
                        lambda table, rows: records.append((table, rows)) or len(rows))
    monkeypatch.setattr(mirror, "verify_counts",
                        lambda expected: {"tiom_despatch_trip": 2})
    result = mirror.sync("token")
    assert result["despatchChanges"] == 1
    assert records == [("tiom_despatch_trip",[{"epass_no": "X", "net_mt": 10}])]
    assert saved["state"]["cursor"] == 103
    assert result["wbSyncUntouched"] is True


def test_denies_any_wb_table_even_if_called_explicitly(mirror):
    with pytest.raises(RuntimeError, match="Non-Despatch"):
        mirror.save_rows("wb_movement", [{"movement_no": "1"}])
    with pytest.raises(RuntimeError, match="Non-Despatch"):
        mirror.remove_row("wb_movement", {"movement_no": "1"})


def test_installer_never_overwrites_existing_wb_sync_code():
    content=(Path(__file__).parents[1] / "scripts" /
             "install_pc_despatch_independent.ps1").read_text(encoding="utf-8")
    # New runner and feature UI only, not old sync core.
    assert "pc_despatch_mirror_standalone.py" in content
    assert "data\\despatch_addon" in content
    assert "app.include_router(tiom_despatch.router)" in content
    assert "schtasks.exe /Create" in content
    assert "git reset" not in content.lower()
    assert "git merge" not in content.lower()
    assert "scripts\\pull_render_sync.py" not in content
