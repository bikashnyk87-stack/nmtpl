"""Safe PC source upgrade verifies local sync changes are not discarded."""
from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path
from scripts import repair_pc_despatch_preserve_local as updater
import pytest


def _git(root, *args):
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "Test Sync")
    _git(root, "config", "user.email", "test@example.com")
    (root/"app"/"routers").mkdir(parents=True)
    (root/"app"/"services").mkdir(parents=True)
    (root/"scripts").mkdir()
    files={
        "app/routers/sync.py": "WB_RULE = 1\n",
        "app/services/cloud_sync.py": "SYNC_TABLES = ('wb',)\n",
        "scripts/pull_render_sync.py": "def sync_once():\n    return 'wb'\n",
    }
    for name, body in files.items():
        (root / name).write_text(body, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "baseline")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-u", "origin", "main")
    return root,files


def test_three_way_preserves_pc_customizations_and_remote_despatch(tmp_path):
    root, originals = _project(tmp_path)
    # Simulate upstream main adding Despatch support to the two sync files.
    (_path:=root/"app"/"services"/"cloud_sync.py").write_text(
        originals["app/services/cloud_sync.py"]+
        "DESPATCH=('tiom_despatch_trip','tiom_despatch_sender','tiom_despatch_permit_day')\n",
        encoding="utf-8")
    (root/"scripts"/"pull_render_sync.py").write_text(
        originals["scripts/pull_render_sync.py"]+
        "DESPATCH_MIRROR_TABLES=()\ndef _ensure_despatch_local_schema(): pass\n"
        "def _repair_despatch_baseline(): pass\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "remote despatch implementation")
    _git(root, "push", "origin", "main")
    _git(root, "reset", "--hard", "HEAD~1")
    # Simulate WB customizations added after the PC baseline.
    (root/"app"/"services"/"cloud_sync.py").write_text(
        "PC_WB_CUSTOM=True\n" + originals["app/services/cloud_sync.py"],encoding="utf-8")
    (root/"scripts"/"pull_render_sync.py").write_text(
        "PC_LOCAL_WB_FIX=True\n"+originals["scripts/pull_render_sync.py"],encoding="utf-8")
    (root/"app"/"routers"/"sync.py").write_text(
        originals["app/routers/sync.py"]+"PC_TWO_WAY_SYNC=True\n",encoding="utf-8")
    with pytest.raises(RuntimeError, match="Unexpected Git origin"):
        updater.preflight(root)
    # PC origin is intentionally restricted to the official repo. The
    # merge helper itself can be tested against an isolated fake remote.
    with tempfile.TemporaryDirectory() as workspace:
        temp = Path(workspace)
        for i, file in enumerate(updater.PROTECTED):
            sub = temp / str(i)
            sub.mkdir()
            output=updater.merged_content(root,sub,file).decode("utf-8")
            assert "PC_" in output
            if file.endswith("cloud_sync.py"):
                assert "tiom_despatch_trip" in output
            if file.endswith("pull_render_sync.py"):
                assert "_repair_despatch_baseline" in output
    assert "PC_LOCAL_WB_FIX" in (root/"scripts"/"pull_render_sync.py").read_text()


def test_preflight_rejects_unexpected_local_modifications(tmp_path,monkeypatch):
    root,_ = _project(tmp_path)
    _git(root,"remote","set-url","origin","https://github.com/bikashnyk87-stack/nmtpl.git")
    # Production never tries to update arbitrary modified source.
    (root/"app"/"routers"/"other.py").write_text("CUSTOM = True\n")
    _git(root,"add","app/routers/other.py")
    with pytest.raises(RuntimeError,match="Additional or unsupported"):
        updater.preflight(root)


@pytest.mark.parametrize("stage_router,stage_worker",[
    (False, False),  # all unstaged; leading porcelain space must survive
    (True, False),   # exactly what the PC may have: first staged
    (False, True),   # other mixed index/worktree state
    (True, True),    # all supported changes staged
])
def test_preflight_keeps_porcelain_status_prefix_for_protected_paths(
    tmp_path, stage_router, stage_worker
):
    root, original = _project(tmp_path)
    _git(root, "remote", "set-url", "origin",
         "https://github.com/bikashnyk87-stack/nmtpl.git")
    router = "app/routers/sync.py"
    cloud = "app/services/cloud_sync.py"
    worker = "scripts/pull_render_sync.py"
    for path in (router, cloud, worker):
        (root / path).write_text(
            original[path] + "\n# LOCAL PC WB CUSTOMIZATION\n", encoding="utf-8"
        )
    if stage_router:
        _git(root, "add", router)
    if stage_worker:
        _git(root, "add", worker)
    status = updater.preflight(root)
    expected_router = "M " if stage_router else " M"
    expected_worker = "M " if stage_worker else " M"
    assert status.startswith(expected_router + " " + router)
    assert (" M " + cloud) in status
    assert (expected_worker + " " + worker) in status
    assert len(status.splitlines()) == 3
