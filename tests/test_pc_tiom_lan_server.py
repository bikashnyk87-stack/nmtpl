"""LAN server starts silently without touching WB/Despatch sync or public firewall."""
from pathlib import Path
import importlib.util
import sys
import types

ROOT=Path(__file__).parents[1]
RUNNER=ROOT/"scripts"/"pc_tiom_lan_runner.py"
INSTALLER=ROOT/"scripts"/"install_pc_tiom_lan.ps1"


def test_lan_install_security_and_isolation():
    text=INSTALLER.read_text(encoding="utf-8")
    assert 'Profile="Private"' in text
    assert 'RemoteAddress="LocalSubnet"' in text
    assert 'LocalPort=8765' in text
    assert 'Program=$pythonw' in text
    assert "New-ScheduledTaskTrigger -AtLogOn" in text
    assert 'New-ScheduledTaskPrincipal' in text
    assert 'MultipleInstances IgnoreNew' in text
    assert 'pythonw.exe' in text
    assert 'http://' in text
    assert 'schtasks.exe /Delete' not in text
    assert 'Stop-Process' not in text
    assert 'Set-NetConnectionProfile' not in text
    assert 'scripts/pull_render_sync.py' not in text
    assert 'app/services/cloud_sync.py' not in text
    assert 'app/routers/sync.py' not in text


def test_lan_runner_binds_expected_port_with_output_to_log(tmp_path, monkeypatch):
    fake_project=tmp_path/"PC"
    (fake_project/"app").mkdir(parents=True)
    (fake_project/"data"/"lan_server").mkdir(parents=True)
    (fake_project/"app"/"main.py").write_text("app = None",encoding="utf-8")
    copied=fake_project/"data"/"lan_server"/"pc_tiom_lan_runner.py"
    copied.write_bytes(RUNNER.read_bytes())
    called={}
    stub=types.ModuleType("uvicorn")
    stub.run=lambda app,**kwargs: called.update({"app":app,**kwargs})
    monkeypatch.setitem(sys.modules,"uvicorn",stub)
    spec=importlib.util.spec_from_file_location("local_tiom_8765_test",copied)
    module=importlib.util.module_from_spec(spec)
    old=Path.cwd()
    try:
        spec.loader.exec_module(module)
        module.main()
    finally:
        monkeypatch.chdir(old)
    assert called == {
        "app":"app.main:app", "host":"0.0.0.0", "port":8765,
        "log_level":"info", "access_log":False, "proxy_headers":False,
    }
    log=(fake_project/"logs"/"lan_server"/"uvicorn_8765.log").read_text(encoding="utf-8")
    assert "TIOM_LAN_SERVER_START" in log
