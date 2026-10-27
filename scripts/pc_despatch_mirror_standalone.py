"""Independent Render -> PC Despatch mirror, preserving the working WB sync.

Runs through the already-paired, authenticated /api/sync snapshot/change feed.
It NEVER imports, edits or calls scripts/pull_render_sync.py, cloud_sync.py or
routers/sync.py, and NEVER resets their cursors or touches WB tables.

Windows installation lives in PC data/despatch_addon/, independent of Git main.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(os.environ.get(
    "NMTPL_PC_PROJECT_ROOT",
    r"E:\NMTPL_Server_v0_1_Laptop_Test\NMTPL_Server_v0_1",
)).resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Integer, MetaData, Numeric, String, Table,
    Text, Time, inspect, text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import make_url

from app.config import settings
from app.db import engine

ADDON = ROOT / "data" / "despatch_addon"
CONFIG = ROOT / "config" / "render_sync_client.json"
STATE = ADDON / "mirror_state.json"
STATUS = ADDON / "mirror_status.json"
LOCK = ADDON / "mirror.lock"
TABLE_NAMES = (
    "tiom_despatch_sender", "tiom_despatch_trip",
    "tiom_despatch_permit_day", "tiom_despatch_audit",
)
REMOTE = "https://nmtpl-tiom-test.onrender.com"
ADDON.mkdir(parents=True, exist_ok=True)
log = logging.getLogger("nmtpl.pc.despatch")


def schema():
    m = MetaData()
    Table("tiom_despatch_sender", m,
          Column("email", String(200), primary_key=True),
          Column("name", String(160), nullable=False),
          Column("active", Boolean, nullable=False),
          Column("created_at", DateTime(timezone=True), nullable=False))
    Table("tiom_despatch_trip", m,
          Column("epass_no", String(120), primary_key=True),
          Column("report_date", Date, nullable=False, index=True),
          Column("permit_no", String(80), nullable=False, index=True),
          Column("permit_qty", Numeric(14, 3)),
          Column("buyer", String(240)),
          Column("vehicle_no", String(80)),
          Column("transporter", String(240)),
          Column("destination", String(240)),
          Column("material_grade", String(160)),
          Column("stack_no", String(100)),
          Column("consignee", String(300)),
          Column("tare_mt", Numeric(12, 3)),
          Column("gross_mt", Numeric(12, 3)),
          Column("net_mt", Numeric(12, 3)),
          Column("dispatch_time", String(80)),
          Column("status", String(24), nullable=False, index=True),
          Column("source", String(200)),
          Column("updated_at", DateTime(timezone=True)))
    Table("tiom_despatch_permit_day", m,
          Column("id", Integer, primary_key=True, autoincrement=True),
          Column("report_date", Date, nullable=False, index=True),
          Column("permit_no", String(80), nullable=False, index=True),
          Column("buyer", String(200)),
          Column("destination", String(200)),
          Column("material", String(120)),
          Column("grade_percent", String(40)),
          Column("permit_qty", Numeric(14, 3)),
          Column("reported_trips", Integer),
          Column("reported_mt", Numeric(14, 3)),
          Column("balance_mt", Numeric(14, 3)),
          Column("document_id", String(40)),
          Column("review_status", String(30)))
    Table("tiom_despatch_audit", m,
          Column("id", Integer, primary_key=True, autoincrement=True),
          Column("changed_at", DateTime(timezone=True)),
          Column("actor", String(80), nullable=False),
          Column("action", String(40), nullable=False),
          Column("entity_key", String(160), nullable=False),
          Column("reason", Text),
          Column("before_json", Text),
          Column("after_json", Text))
    return m


def assert_safe_destination():
    database_url = make_url(settings.database_url)
    if database_url.get_backend_name() != "postgresql" or (
        database_url.host or ""
    ).lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(
            "Safety stop: Despatch mirror may write ONLY to the local PC PostgreSQL."
        )


def get_config():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    if str(cfg.get("base_url", "")).rstrip("/") != REMOTE:
        raise RuntimeError("Refusing to send the sync token to an unexpected URL.")
    token = str(cfg.get("token") or "")
    if len(token) < 30:
        raise RuntimeError("The PC is not yet paired with Render.")
    return cfg, token


def get(path, token):
    req = urllib.request.Request(
        REMOTE + path,
        headers={"X-NMTPL-Sync-Token": token,
                 "User-Agent": "NMTPL-Despatch-Independent-Mirror/1.0"},
    )
    # All reads use the existing pairing; never expose credentials to logs.
    with urllib.request.urlopen(req, timeout=120) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected Render sync response.")
    return data


def manifest(token):
    result = get("/api/sync/snapshot-manifest", token)
    missing = sorted(set(TABLE_NAMES) - set(result.get("tables") or ()))
    if missing:
        raise RuntimeError("Render has not exposed Despatch mirror tables: " +
                           ", ".join(missing))
    return result


def source_snapshot(name, offset, token):
    q = urllib.parse.urlencode({"offset": offset, "limit": 500})
    return get(f"/api/sync/snapshot/{name}?{q}", token)


def change_feed(after, token):
    q = urllib.parse.urlencode({"after": after, "limit": 500})
    return get("/api/sync/changes?" + q, token)


def load_state():
    if not STATE.exists():
        return {}
    doc = json.loads(STATE.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise RuntimeError("Invalid independent Despatch checkpoint.")
    return doc


def atomic_write(path, document):
    fd, temporary = tempfile.mkstemp(prefix="despatch-", suffix=".json", dir=ADDON)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(document, f, indent=2, default=str)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def convert(col, val):
    if val is None:
        return None
    if isinstance(col.type, DateTime) and isinstance(val, str):
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    if isinstance(col.type, Date) and not isinstance(col.type, DateTime) and isinstance(val, str):
        return date.fromisoformat(val[:10])
    if isinstance(col.type, Time) and isinstance(val, str):
        return time.fromisoformat(val)
    if isinstance(col.type, Numeric) and not isinstance(val, Decimal):
        return Decimal(str(val))
    return val


def check_schema():
    assert_safe_destination()
    models = schema()
    models.create_all(engine, checkfirst=True)
    with engine.connect() as conn:
        existing = set(inspect(conn).get_table_names())
        for name in TABLE_NAMES:
            if name not in existing:
                raise RuntimeError("Local Despatch table not created: " + name)
            reflected = Table(name, MetaData(), autoload_with=conn)
            required = models.tables[name]
            diff = set(required.c.keys()) - set(reflected.c.keys())
            if diff:
                raise RuntimeError("Local Despatch schema is missing columns on "+
                                   name+": "+", ".join(sorted(diff)))


def save_rows(name, source_rows):
    if not source_rows:
        return 0
    if name not in TABLE_NAMES:
        raise RuntimeError("Non-Despatch table denied.")
    with engine.begin() as conn:
        # Prevent PC->Render change tracking for rows copied FROM Render.
        conn.execute(text("SELECT set_config('nmtpl.sync_apply','on',true)"))
        table = Table(name, MetaData(), autoload_with=conn)
        keys = [col.name for col in table.primary_key]
        prepared = []
        for raw in source_rows:
            if not isinstance(raw, dict):
                raise RuntimeError("Invalid Render snapshot row.")
            if set(raw) - set(table.c.keys()):
                raise RuntimeError("Source/schema column mismatch in " + name)
            row = {key: convert(table.c[key], val) for key,val in raw.items()}
            if any(row.get(key) is None for key in keys):
                raise RuntimeError("Missing Despatch primary key in " + name)
            prepared.append(row)
        # 100 inserts/txn avoids giant SQL packets while retaining atomicity.
        for start in range(0, len(prepared), 100):
            batch = prepared[start:start+100]
            stmt = pg_insert(table).values(batch)
            changed = {key: getattr(stmt.excluded, key)
                       for key in batch[0] if key not in keys}
            if changed:
                stmt = stmt.on_conflict_do_update(
                    index_elements=[table.c[key] for key in keys],
                    set_=changed,
                )
            else:
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=[table.c[key] for key in keys]
                )
            conn.execute(stmt)
    return len(source_rows)


def remove_row(name, raw):
    if name not in TABLE_NAMES:
        raise RuntimeError("Non-Despatch delete denied.")
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('nmtpl.sync_apply','on',true)"))
        table = Table(name, MetaData(), autoload_with=conn)
        keys = [col.name for col in table.primary_key]
        if any(key not in raw for key in keys):
            raise RuntimeError("Missing delete key for " + name)
        terms = [table.c[key] == convert(table.c[key], raw[key]) for key in keys]
        conn.execute(table.delete().where(*terms))


def count_local():
    with engine.connect() as conn:
        return {
            name: int(conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar() or 0)
            for name in TABLE_NAMES
        }


def verify_counts(expected):
    present = count_local()
    mismatches = {
        n: {"render": int(expected[n]), "pc": present[n]}
        for n in TABLE_NAMES if n in expected and int(expected[n]) != present[n]
    }
    if mismatches:
        raise RuntimeError(
            "Despatch-only row count mismatch (no WB data was touched): " +
            json.dumps(mismatches)
        )
    return present


def snapshot_all(token, first_manifest):
    counts = {}
    watermark = int(first_manifest.get("watermark", 0))
    for name in TABLE_NAMES:
        offset = 0
        count = 0
        while True:
            data = source_snapshot(name, offset, token)
            rows = data.get("rows") or []
            count += save_rows(name, rows)
            if not data.get("hasMore"):
                break
            next_offset = data.get("nextOffset")
            if next_offset is None or int(next_offset) <= offset:
                raise RuntimeError(f"Snapshot pagination stopped at {name} #{offset}")
            offset = int(next_offset)
        counts[name] = count
        log.info("Mirrored Render Despatch %s: %s rows", name, count)
    # Sequence check must run after snapshot IDs have been restored.
    with engine.begin() as conn:
        for name in ("tiom_despatch_permit_day", "tiom_despatch_audit"):
            seq = conn.execute(
                text("SELECT pg_get_serial_sequence(:name, 'id')"),
                {"name": f"public.{name}"},
            ).scalar()
            if seq:
                conn.execute(text(
                    f"SELECT setval(CAST(:sequence AS regclass), "
                    f"GREATEST((SELECT COALESCE(MAX(id),0) FROM {name}),1), "
                    f"(SELECT COUNT(*) > 0 FROM {name}))"
                ), {"sequence": seq})
    return watermark, counts


def sync(token, *, max_pages=500):
    check_schema()
    state = load_state()
    initial = not bool(state.get("baseline_complete"))
    initial_counts = {}
    if initial:
        first_manifest = manifest(token)
        watermark, initial_counts = snapshot_all(token, first_manifest)
        # Only the separate Despatch state is written; no WB cursor touched.
        state = {"baseline_complete": True, "cursor": watermark}
        atomic_write(STATE, state)
    cursor = int(state.get("cursor", 0))
    pulled = 0
    pages = 0
    changes_seen = 0
    while pages < max_pages:
        upstream = manifest(token)
        target = int(upstream.get("watermark", cursor))
        if cursor >= target:
            break
        payload = change_feed(cursor, token)
        events = payload.get("changes") or []
        new_cursor = int(payload.get("lastChangeId", cursor))
        if new_cursor <= cursor and target > cursor:
            raise RuntimeError("Render sync cursor did not advance.")
        for event in events:
            name = event.get("table")
            if name not in TABLE_NAMES:
                continue
            op = event.get("operation")
            row = event.get("row") or {}
            if op == "D":
                remove_row(name, row)
            elif op in {"I", "U"}:
                save_rows(name, [row])
            else:
                raise RuntimeError("Unexpected Despatch sync operation: "+str(op))
            changes_seen += 1
        cursor = new_cursor
        state["cursor"] = cursor
        atomic_write(STATE, state)
        pages += 1
        if not payload.get("hasMore") and cursor >= target:
            break
    if pages >= max_pages:
        raise RuntimeError("Despatch incremental sync exceeded page safety limit.")
    final = manifest(token)
    counts = verify_counts(final.get("despatchRowCounts") or {})
    return {
        "ok": True, "despatchOnly": True,
        "freshSnapshot": initial,
        "snapshotRows": initial_counts,
        "localTables": counts,
        "cursor": cursor,
        "despatchChanges": changes_seen,
        "wbSyncUntouched": True,
        "lastVerified": datetime.now(timezone.utc).isoformat(),
    }


def main():
    assert_safe_destination()
    cfg, token = get_config()
    import msvcrt
    with LOCK.open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print(json.dumps({"busy": True, "message": "A Despatch-only sync is already running."}))
            return 3
        try:
            result = sync(token)
            atomic_write(STATUS, result)
            print(json.dumps(result))
            return 0
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            atomic_write(STATUS, {
                "ok": False, "error": msg, "time": datetime.now(timezone.utc).isoformat(),
                "wbSyncUntouched": True,
            })
            print("Despatch-only PC sync failed:", msg)
            return 1
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == "__main__":
    sys.exit(main())
