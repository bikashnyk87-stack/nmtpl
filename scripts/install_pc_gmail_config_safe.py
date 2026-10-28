"""Apply PC Gmail config UI safely without replacing the working TIOM/WB app.

Downloads only approved files from the NMTPL GitHub repository. Existing local
automation.py and Despatch router are PATCHED surgically; WB sync and data are
never touched. Keep backups, preserve local modifications elsewhere.
"""
from __future__ import annotations
import ast
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.request import urlopen

DEFAULT_ROOT = Path(r"E:\NMTPL_Server_v0_1_Laptop_Test\NMTPL_Server_v0_1")
RAW = "https://raw.githubusercontent.com/bikashnyk87-stack/nmtpl/main/"
BACKUP_DIR = "backups"
AUTOMATION = "app/routers/automation.py"
DESPATCH = "app/routers/tiom_despatch.py"
JS = "app/static/tiom_despatch.js"
INDEX = "app/static/index.html"
FILES = (AUTOMATION, DESPATCH, JS, INDEX)


def section(value: str, start: str, end: str) -> str:
    a = value.find(start)
    b = value.find(end, a + len(start))
    if a < 0 or b < 0:
        raise RuntimeError("Safe patch anchor missing: " + start)
    return value[a:b]


def patch(current: dict[str, str], upstream: dict[str, str]) -> dict[str, str]:
    """Preflight all four files in memory before modifying anything."""
    out = dict(current)
    token_start, token_end = "def _gmail_token_raw() -> str:", "def _prepare_gmail_token()"
    current_token = section(current[AUTOMATION], token_start, token_end)
    new_token = section(upstream[AUTOMATION], token_start, token_end)
    out[AUTOMATION] = current[AUTOMATION].replace(current_token, new_token, 1)

    router_end = '@router.post("/mail-sync")'
    router_start = '@router.get("/mail-status")'
    original = section(current[DESPATCH], router_start, router_end)
    new = section(upstream[DESPATCH], "def _local_gmail_setup_allowed(", router_end)
    if "def _local_gmail_setup_allowed(" in current[DESPATCH]:
        old_start = "def _local_gmail_setup_allowed("
        original = section(current[DESPATCH], old_start, router_end)
    out[DESPATCH] = current[DESPATCH].replace(original, new, 1)
    if "UploadFile" not in current[DESPATCH] or "File" not in current[DESPATCH]:
        raise RuntimeError("PC Despatch router upload dependencies do not match current installer.")

    if "window.tiomDDPanel" not in current[JS]:
        raise RuntimeError("Expected existing Despatch frontend missing. No changes made.")
    out[JS] = upstream[JS]
    # Invalidate immutable Javascript browser caches, without changing other UI.
    old_html=current[INDEX]
    pattern=r'(/static/tiom_despatch\.js\?v=)[^"''< ]+'
    html, count = re.subn(pattern, r'\g<1>pc-gmail-config-v2', old_html)
    if count == 0:
        raise RuntimeError("Despatch script tag not present in local index.html.")
    out[INDEX] = html

    for name in (AUTOMATION, DESPATCH):
        ast.parse(out[name], filename=name)
    # No changes to sync.py, cloud_sync.py, WB worker, main.py, DB, tokens.
    assert "gmailTokenConfigured" in out[DESPATCH]
    assert "gmail-connect-local" in out[DESPATCH]
    assert 'config" / "gmail_token.json"' in out[AUTOMATION]
    assert "tiomDDGmailConnect" in out[JS]
    return out


def install(root: Path, *, source_dir: Path | None = None) -> None:
    """Read staged PowerShell downloads if available; no Python network use."""
    root = root.resolve()
    old = {name: (root / name).read_text(encoding="utf-8-sig") for name in FILES}
    fresh = {}
    for name in (AUTOMATION, DESPATCH, JS):
        if source_dir is not None:
            candidate = source_dir.resolve() / name
            if not candidate.is_file() or candidate.stat().st_size > 256_000:
                raise RuntimeError(f"Invalid/missing staged file: {name}. Nothing changed.")
            fresh[name] = candidate.read_text(encoding="utf-8-sig")
        else:
            with urlopen(RAW + name, timeout=120) as response:
                fresh[name] = response.read(256_001).decode("utf-8-sig")
            if len(fresh[name]) > 256_000:
                raise RuntimeError(f"Upstream file too large: {name}. Nothing changed.")
    changes = patch(old, fresh)
    backup = root / BACKUP_DIR / ("gmail_pc_safe_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    for name in FILES:
        target = backup / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    applied = []
    try:
        for name in FILES:
            if changes[name] == old[name]:
                continue
            target = root / name
            fd, temp = tempfile.mkstemp(prefix=".gmail_pc_", dir=target.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                    f.write(changes[name])
                os.replace(temp, target)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            applied.append(name)
    except Exception:
        for name in applied:
            shutil.copy2(backup / name, root / name)
        raise
    print("SUCCESS: PC MIS Gmail configuration UI added.")
    print("Backup:", backup)
    print("Files updated:", ", ".join(applied) or "(already current)")
    print("WB/Despatch sync, database, and existing OAuth credentials UNCHANGED.")
    print("Restart your local TIOM 8765 task to load Python router changes.")
    print("Then open http://127.0.0.1:8765/tiom -> Production -> Despatch Report -> Mail & Image Imports.")
    print("The Gmail Connect control accepts an authorized OAuth token JSON for mistiom@nmtpl.com.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Safely install the PC Despatch Gmail connection UI")
    parser.add_argument("--source-dir", type=Path, help="PowerShell predownloaded files; no Python network calls")
    parser.add_argument("--project-root", type=Path, default=Path(os.environ.get("NMTPL_PC_PROJECT_ROOT", str(DEFAULT_ROOT))))
    args = parser.parse_args()
    install(args.project_root, source_dir=args.source_dir)
