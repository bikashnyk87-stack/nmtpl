"""Non-destructive PC TIOM code upgrade preserving three local WB/sync customizations.

Usage (from Windows PowerShell):
  python "%TEMP%\repair_pc_despatch_preserve_local.py"

This tool will abort BEFORE changing tracked files if:
  - there are changed tracked files outside the three known sync files,
  - any of the three edits conflict with latest GitHub main,
  - the merged Python code has syntax errors or lacks expected Despatch hooks,
  - the local branch cannot be fast-forwarded.

Keeps a dated backup and the original Git stash. Never resets a Git branch,
drops tables or rewrites Render/PC sync state.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback

DEFAULT_ROOT = Path(r"E:\NMTPL_Server_v0_1_Laptop_Test\NMTPL_Server_v0_1")
PROTECTED = (
    "app/routers/sync.py",
    "app/services/cloud_sync.py",
    "scripts/pull_render_sync.py",
)
REQUIRED = {
    "app/services/cloud_sync.py": (
        "tiom_despatch_trip", "tiom_despatch_sender", "tiom_despatch_permit_day"
    ),
    "scripts/pull_render_sync.py": (
        "_ensure_despatch_local_schema", "_repair_despatch_baseline",
        "DESPATCH_MIRROR_TABLES",
    ),
}
BACKUP_STATES = (
    "data/render_sync_state.json",
    "data/render_push_state.json",
    "data/render_despatch_backfill.json",
)
OFFICIAL_REPO = "bikashnyk87-stack/nmtpl"
APP_TIMEOUT = 120


def git(root: Path, *args: str, check=True) -> subprocess.CompletedProcess:
    cmd = ["git", "-C", str(root), *args]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and proc.returncode:
        raise RuntimeError(
            "Git " + " ".join(args[:3]) + " failed:\n" +
            proc.stderr.decode("utf-8", "replace")[-1500:]
        )
    return proc


def decode(b: bytes) -> str:
    return b.decode("utf-8", "replace").strip()


def copy_backup(root: Path, dest: Path, name: str):
    src = root / name
    if src.is_file():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


def preflight(root: Path):
    if not root.is_dir() or not (root / ".git").exists():
        raise RuntimeError("Expected Git checkout missing: " + str(root))
    branch = decode(git(root, "branch", "--show-current").stdout)
    if branch != "main":
        raise RuntimeError(f"Local branch is {branch!r}; refusing to alter anything other than main")
    url = decode(git(root, "remote", "get-url", "origin").stdout).lower().removesuffix(".git")
    if OFFICIAL_REPO not in url or not (
        url.startswith("https://github.com/") or
        url.startswith("git@github.com:") or url.startswith("ssh://git@github.com/")
    ):
        raise RuntimeError("Unexpected Git origin; refusing source update")
    changes = decode(git(root, "status", "--porcelain=v1", "--untracked-files=no").stdout)
    if not changes:
        print("Tracked sources are clean; using ordinary fast-forward instead.")
        return changes
    modified = {}
    for line in changes.splitlines():
        flag, path = line[:2], line[3:]
        if path not in PROTECTED or flag != " M":
            raise RuntimeError(
                "Additional or staged Git changes detected; no tracked source was changed:\n" +
                changes
            )
        modified[path] = True
    print("Protected local modifications:", ", ".join(modified))
    return changes


def merged_content(root: Path, location: Path, path: str) -> bytes:
    base = git(root, "show", f"HEAD:{path}").stdout
    theirs = git(root, "show", f"origin/main:{path}").stdout
    ours = (root / path).read_bytes()
    base_file = location / "base"
    local_file = location / "local"
    cloud_file = location / "remote"
    base_file.write_bytes(base)
    local_file.write_bytes(ours)
    cloud_file.write_bytes(theirs)
    result = subprocess.run(
        ["git", "merge-file", "-p",
         "-L", "LOCAL-PC", "-L", "ORIGINAL-BASE", "-L", "GITHUB-MAIN",
         str(local_file), str(base_file), str(cloud_file)],
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(
            "Three-way merge CONFLICT in " + path +
            ". No tracked files or sync data were changed. Backup kept for review."
        )
    try:
        ast.parse(result.stdout.decode("utf-8-sig"), filename=path)
    except SyntaxError as exc:
        raise RuntimeError(f"Unsafe merged Python syntax in {path}: {exc}") from exc
    for marker in REQUIRED.get(path, ()):
        if marker not in result.stdout.decode("utf-8", "replace"):
            raise RuntimeError("Required Despatch functionality absent from merged " + path + ": " + marker)
    return result.stdout


def run_upgrade(root: Path) -> int:
    state = preflight(root)
    backups = root / "backups" / ("despatch_safe_merge_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    backups.mkdir(parents=True, exist_ok=True)
    for name in PROTECTED + BACKUP_STATES:
        copy_backup(root, backups, name)
    (backups / "git_tracked_changes.txt").write_text(state, encoding="utf-8")
    (backups / "source_commit_before.txt").write_text(
        decode(git(root, "rev-parse", "HEAD").stdout), encoding="utf-8"
    )
    print("Backup:", backups)

    print("Fetching latest TIOM application files from GitHub...")
    git(root, "fetch", "--prune", "origin", "main")
    if git(root, "merge-base", "--is-ancestor", "HEAD", "origin/main", check=False).returncode:
        raise RuntimeError(
            "PC branch diverges from origin/main. No source merge attempted; manual review required."
        )

    merged = {}
    with tempfile.TemporaryDirectory(prefix="nmtpl_despatch_merge_") as tmp:
        work = Path(tmp)
        for index, name in enumerate(PROTECTED):
            workspace = work / str(index)
            workspace.mkdir()
            merged[name] = merged_content(root, workspace, name)
            (backups / (name.replace("/", "__") + ".merged.preview.py")).write_bytes(merged[name])
    print("Three protected files have a conflict-free, syntax-checked merge.")
    print("WB/PC customization backup saved. Sync cursors will not be reset.")

    # Take an additional working-tree check before the only mutating Git step.
    if preflight(root) != state:
        raise RuntimeError("Local Git files changed during preparation; aborting without touching them")

    stash_sha = None
    changed = bool(state.strip())
    if changed:
        print("Safely stashing only the three known modified sync files...")
        git(root, "stash", "push", "-m", "PC sync customizations before Despatch safe merge",
            "--", *PROTECTED)
        stash_sha = decode(git(root, "rev-parse", "refs/stash").stdout)
        (backups / "original_local_stash_sha.txt").write_text(stash_sha, encoding="utf-8")
    try:
        print("Fast-forwarding Git main without forced reset...")
        git(root, "merge", "--ff-only", "origin/main")
    except Exception:
        if stash_sha:
            print("Git update failed; restoring local modifications from saved stash...")
            apply = git(root, "stash", "apply", stash_sha, check=False)
            if apply.returncode:
                print("Stash restore needs manual attention. Originals remain in backup:", backups)
        raise

    # This replaces only three protected SOURCE files after calculating a
    # clean three-way merge. All databases, tokens, sync watermarks and settings
    # are never modified by this step.
    for name, data in merged.items():
        target = root / name
        tmp_file = target.with_suffix(target.suffix + ".despatch-temp")
        tmp_file.write_bytes(data)
        os.replace(tmp_file, target)
    print("PC source updated and local changes preserved.")
    if stash_sha:
        print("Original custom code is also retained in Git stash", stash_sha)

    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    print("Running Despatch and WB synchronization using the existing PC Python environment...")
    # The updated sync worker contains its own file lock (also used by the
    # scheduled task). A lock-busy result must not be mistaken for success.
    cmd = [str(python), str(root / "scripts" / "pull_render_sync.py")]
    proc = subprocess.run(cmd, cwd=str(root), env=env, capture_output=True,
                          text=True, errors="replace", timeout=600)
    if proc.stdout:
        print(proc.stdout[-7500:])
    if proc.stderr:
        print("Diagnostics:", proc.stderr[-1500:])
    if proc.returncode:
        print("Sync was not confirmed. Existing sync credentials/state were not reset.")
        print("See logs/render_sync/worker.log and backup", backups)
        return 2
    try:
        final = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        final = {}
    if final.get("busy"):
        print("Scheduled sync already running. Let it finish and run the check below.")
        return 3
    if not (final.get("despatch_repair") or {}).get("complete"):
        print("Despatch backfill not yet verified. Use the check script; WB remains protected.")
        return 3

    diagnostic = subprocess.run(
        [str(python), str(root / "scripts" / "check_pc_despatch_sync.py")],
        cwd=str(root), env=env, capture_output=True, text=True,
        errors="replace", timeout=APP_TIMEOUT,
    )
    print(diagnostic.stdout[-6000:] if diagnostic.stdout else "")
    if diagnostic.returncode:
        print("PC data check remains incomplete; review diagnostics, no WB reset performed.")
        return 3
    print("SUCCESS: PC Despatch tables, historical rows and normal sync verified.")
    print("Restart the local TIOM server only after reviewing any preserved custom code.")
    return 0


def main():
    root = Path(os.getenv("NMTPL_PC_PROJECT_ROOT", str(DEFAULT_ROOT)))
    try:
        return run_upgrade(root)
    except Exception as exc:
        print("SAFE STOP:", exc)
        print("No destructive Git reset, database deletion or watermark reset was used.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
