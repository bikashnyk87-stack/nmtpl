"""TIOM port 8765 starts silently on login, never exposing a Public Wi-Fi port."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import types

RUNNER=Path(__file__).parents[1]/"scripts"/"pc_tiom_local_8765_runner.py"
INSTALLER=Path(__file__).parents[1]/"scripts"/"install_pc_tiom_local_autostart.ps1"


def test_local_autostart_installer_does_not_change_wb_or_windows_network():
    text=INSTALLER.read_text(encoding="utf-8")
    assert "New-ScheduledTaskTrigger -AtLogOn" in text
    assert "New-ScheduledTaskPrincipal" in text
    assert "Register-ScheduledTask" in text
    assert 'pythonw.exe' in text
    assert "MultipleInstances IgnoreNew" in text
    assert '"NMTPL TIOM Local 8765 - At Logon"' in text
    assert "data\local_server" in text
    assert "Get-NetTCPConnection" in text
    for forbidden in (
        "New-NetFirewallRule", "Set-NetConnectionProfile", "Stop-Process",
        "git reset", "git merge", "scripts/pull_render_sync.py",
        "scripts/wb_gmail_worker.py", "scripts/pc_despatch_mirror_standalone.py",
    ):
        assert forbidden not in text


def test_local_runner_binds_only_loopback_and_logs(tmp_path, monkeypatch):
    pc=tmp_path/"pc"
    (pc/"app").mkdir(parents=True)
    (pc/"app"/"main.py").write_text("app=None", encoding="utf-8")
    folder=pc/"data"/"local_server"
    folder.mkdir(parents=True)
    temp=folder/"pc_tiom_local_8765_runner.py"
    temp.write_bytes(RUNNER.read_bytes())
    call={}
    stub=types.ModuleType("uvicorn")
    stub.run=lambda app,**kwargs: call.update({"app":app,**kwargs})
    monkeypatch.setitem(sys.modules,"uvicorn",stub)
    spec=importlib.util.spec_from_file_location("test_local_8765",temp)
    mod=importlib.util.module_from_spec(spec)
    prior=Path.cwd()
    try:
        spec.loader.exec_module(mod)
        mod.main()
    finally:
        os.chdir(prior)
    assert call == {
        "app":"app.main:app", "host":"127.0.0.1", "port":8765,
        "access_log":False, "proxy_headers":False, "log_level":"info",
    }
    output=(pc/"logs"/"local_server"/"uvicorn_8765.log").read_text(encoding="utf-8")
    assert "LOCAL_TIOM_8765_START=" in output
