"""Office LAN upgrade reuses verified 8765 task and never touches WB sync."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"enable_pc_tiom_office_lan.ps1"


def test_upgrade_existing_task_not_second_runner():
    s=SCRIPT.read_text(encoding="utf-8")
    assert 'NMTPL TIOM Local 8765 - At Logon' in s
    assert 'Set-ScheduledTask -TaskName $taskName -Action $action' in s
    assert 'New-ScheduledTaskAction' in s
    assert 'Register-ScheduledTask' not in s
    assert 'NMTPL TIOM LAN Server - At Logon' not in s
    assert 'Stop-ScheduledTask -TaskName $taskName' in s
    assert 'Stop-Process' not in s
    assert 'taskschd' not in s.lower()


def test_upgrade_requires_trusted_wifi_and_private_firewall():
    s=SCRIPT.read_text(encoding="utf-8")
    assert 'Read-Host' in s
    assert 'TRUSTED-OFFICE' in s
    assert 'Set-NetConnectionProfile -InterfaceIndex $profile.InterfaceIndex -NetworkCategory Private' in s
    assert 'Get-NetConnectionProfile -InterfaceAlias $InterfaceAlias' in s
    assert 'Profile="Private,Domain"' in s
    assert 'RemoteAddress="LocalSubnet"' in s
    assert 'LocalAddress=$lanIp' in s
    assert 'InterfaceAlias=$InterfaceAlias' in s
    assert 'Program=$pythonw' in s
    assert 'LocalPort=8765' in s
    assert 'LAN_HTTP_HEALTH_200_OK' in s
    assert '127.0.0.1:8765/tiom' in s


def test_backup_restore_and_unrelated_sync_isolation():
    s=SCRIPT.read_text(encoding="utf-8")
    assert 'Export-ScheduledTask' in s
    assert 'Set-ScheduledTask -TaskName $taskName -Action $oldAction' in s
    assert 'Get-NetTCPConnection -LocalPort 8765' in s
    assert 'pc_tiom_lan_runner.py' in s
    assert 'pc_tiom_local_8765_runner.py' in s
    for forbidden in (
        "Remove-ScheduledTask", "Unregister-ScheduledTask",
        "scripts/pull_render_sync.py",
        "scripts/pc_despatch_mirror_standalone.py",
        "app/routers/sync.py", "app/services/cloud_sync.py",
        "git reset", "New-ScheduledTaskTrigger",
    ):
        assert forbidden not in s
