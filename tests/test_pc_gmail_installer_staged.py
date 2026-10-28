"""PC Gmail UI install must work from staged files, without any Python network reads."""
from pathlib import Path
import shutil

import scripts.install_pc_gmail_config_safe as installer

ROOT=Path(__file__).resolve().parents[1]


def test_offline_installer_requires_all_source_files_before_changes(tmp_path, monkeypatch):
    dest=tmp_path/"pc"
    stage=tmp_path/"downloads"
    for name in installer.FILES:
        path=dest/name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/name,path)
    for name in (installer.AUTOMATION,installer.DESPATCH):
        path=stage/name
        path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,path)
    before={name:(dest/name).read_bytes() for name in installer.FILES}
    def no_network(*args,**kwargs):
        raise AssertionError("offline install attempted Python URL fetch")
    monkeypatch.setattr(installer,"urlopen",no_network)
    try:
        installer.install(dest,source_dir=stage)
    except RuntimeError as e:
        assert "Invalid/missing staged file" in str(e)
    else:
        raise AssertionError("Missing JS must block all file writes")
    assert all((dest/name).read_bytes()==before[name] for name in installer.FILES)


def test_staged_install_does_not_fetch_and_creates_verified_backup(tmp_path, monkeypatch):
    dest=tmp_path/"pc"
    stage=tmp_path/"downloads"
    for name in installer.FILES:
        target=dest/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,target)
        if name != installer.INDEX:
            staged=stage/name
            staged.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/name,staged)
    monkeypatch.setattr(installer,"urlopen",lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError("network called")))
    installer.install(dest,source_dir=stage)
    assert "pc-gmail-config-v2" in (dest/installer.INDEX).read_text(encoding="utf-8")
    backups=list((dest/"backups").glob("gmail_pc_safe_*"))
    assert len(backups)==1
    for name in installer.FILES:
        assert (backups[0]/name).is_file()


def test_powershell_wrapper_stages_retries_checks_before_applying():
    s=(ROOT/"scripts"/"install_pc_gmail_config_reliable.ps1").read_text(encoding="utf-8")
    assert "-TimeoutSec 180" in s
    assert "$n -le 4" in s
    assert "--source-dir $stage" in s
    assert "All files staged and validated" in s
    assert "Get-ScheduledTask -TaskName $taskName" in s
    assert "gmail-connect-local" in s
    assert "scripts/pull_render_sync.py" not in s
    assert "app/services/cloud_sync.py" not in s
    assert "Remove-ScheduledTask" not in s
    assert "Remove-NetFirewallRule" not in s
