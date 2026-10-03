from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from datetime import date, datetime, time as dtime
from decimal import Decimal
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import Date, DateTime, MetaData, Numeric, Table, Time, delete, inspect
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import make_url

from app.config import settings
from app.db import engine
from app.services.cloud_sync import SYNC_TABLES

CONFIG_PATH = ROOT / "config" / "render_sync_client.json"
STATE_PATH = ROOT / "data" / "render_sync_state.json"
LOG_DIR = ROOT / "logs" / "render_sync"
LOG_PATH = LOG_DIR / "worker.log"
STATUS_PATH = LOG_DIR / "status.json"

LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("render_sync_client")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = RotatingFileHandler(LOG_PATH, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(sh)


def _write_status(**kwargs):
    payload = {"updated_at": datetime.now().astimezone().isoformat(), **kwargs}
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(STATUS_PATH)


def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _save_state(change_id: int, baseline_complete: bool = True):
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "last_change_id": int(change_id),
                "baseline_complete": bool(baseline_complete),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(STATE_PATH)


def _assert_local_database():
    url = make_url(settings.database_url)
    host = (url.host or "").strip().lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(
            "Safety stop: sync may only write to local PostgreSQL. "
            f"Current DATABASE_URL host is {host!r}."
        )


def _get_json(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "X-NMTPL-Sync-Token": token,
            "User-Agent": "NMTPL-Base-PC-Sync/1.1",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_changes(base_url: str, token: str, after_id: int, limit: int = 500) -> dict:
    query = urllib.parse.urlencode({"after": int(after_id), "limit": int(limit)})
    return _get_json(base_url.rstrip("/") + "/api/sync/changes?" + query, token)


def _fetch_snapshot_manifest(base_url: str, token: str) -> dict:
    return _get_json(base_url.rstrip("/") + "/api/sync/snapshot-manifest", token)


def _fetch_snapshot_table(
    base_url: str,
    token: str,
    table_name: str,
    offset: int,
    limit: int = 500,
) -> dict:
    query = urllib.parse.urlencode({"offset": int(offset), "limit": int(limit)})
    safe_name = urllib.parse.quote(table_name, safe="")
    return _get_json(
        base_url.rstrip("/") + f"/api/sync/snapshot/{safe_name}?" + query,
        token,
    )


def _coerce(column, value):
    if value is None:
        return None
    try:
        if isinstance(column.type, DateTime) and isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(column.type, Date) and not isinstance(column.type, DateTime) and isinstance(value, str):
            return date.fromisoformat(value[:10])
        if isinstance(column.type, Time) and isinstance(value, str):
            return dtime.fromisoformat(value)
        if isinstance(column.type, Numeric) and not isinstance(value, Decimal):
            return Decimal(str(value))
    except Exception:
        return value
    return value


def _apply_batch(changes: list[dict]) -> dict:
    metadata = MetaData()
    reflected: dict[str, Table] = {}
    counts = {"insert_or_update": 0, "delete": 0, "skipped": 0}

    with engine.begin() as conn:
        existing_tables = set(inspect(conn).get_table_names())

        for change in changes:
            table_name = str(change.get("table") or "")
            operation = str(change.get("operation") or "").upper()
            raw_row = change.get("row") or {}

            if table_name not in SYNC_TABLES or table_name not in existing_tables:
                counts["skipped"] += 1
                logger.warning("Skipped unrecognized/local-missing table %s", table_name)
                continue

            table = reflected.get(table_name)
            if table is None:
                table = Table(table_name, metadata, autoload_with=conn)
                reflected[table_name] = table

            row = {
                key: _coerce(table.c[key], value)
                for key, value in raw_row.items()
                if key in table.c
            }
            pk_names = [col.name for col in table.primary_key.columns]
            if not pk_names or any(name not in row for name in pk_names):
                raise RuntimeError(
                    f"Cannot sync {table_name}: primary key missing from change payload."
                )

            if operation == "D":
                conditions = [table.c[name] == row[name] for name in pk_names]
                conn.execute(delete(table).where(*conditions))
                counts["delete"] += 1
                continue

            stmt = pg_insert(table).values(**row)
            update_values = {
                key: getattr(stmt.excluded, key)
                for key in row
                if key not in pk_names
            }
            if update_values:
                stmt = stmt.on_conflict_do_update(
                    index_elements=[table.c[name] for name in pk_names],
                    set_=update_values,
                )
            else:
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=[table.c[name] for name in pk_names]
                )
            conn.execute(stmt)
            counts["insert_or_update"] += 1

    return counts


def _apply_snapshot_rows(table_name: str, rows: list[dict]) -> int:
    if not rows:
        return 0

    metadata = MetaData()
    with engine.begin() as conn:
        existing_tables = set(inspect(conn).get_table_names())
        if table_name not in SYNC_TABLES or table_name not in existing_tables:
            logger.warning("Baseline skipped local-missing table %s", table_name)
            return 0

        table = Table(table_name, metadata, autoload_with=conn)
        pk_names = [col.name for col in table.primary_key.columns]
        if not pk_names:
            raise RuntimeError(f"Cannot baseline {table_name}: no primary key.")

        applied = 0
        for raw_row in rows:
            row = {
                key: _coerce(table.c[key], value)
                for key, value in (raw_row or {}).items()
                if key in table.c
            }
            if any(name not in row for name in pk_names):
                raise RuntimeError(
                    f"Cannot baseline {table_name}: primary key missing from row."
                )
            stmt = pg_insert(table).values(**row)
            update_values = {
                key: getattr(stmt.excluded, key)
                for key in row
                if key not in pk_names
            }
            if update_values:
                stmt = stmt.on_conflict_do_update(
                    index_elements=[table.c[name] for name in pk_names],
                    set_=update_values,
                )
            else:
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=[table.c[name] for name in pk_names]
                )
            conn.execute(stmt)
            applied += 1
        return applied


def _bootstrap_baseline(base_url: str, token: str) -> dict:
    manifest = _fetch_snapshot_manifest(base_url, token)
    watermark = int(manifest.get("watermark", 0) or 0)
    tables = manifest.get("tables") or []
    total_rows = 0
    table_counts: dict[str, int] = {}

    logger.info(
        "Starting cloud baseline at watermark %s across %s tables.",
        watermark,
        len(tables),
    )

    for table_name in tables:
        offset = 0
        applied_for_table = 0
        while True:
            payload = _fetch_snapshot_table(
                base_url, token, table_name, offset, limit=500
            )
            rows = payload.get("rows") or []
            applied = _apply_snapshot_rows(table_name, rows)
            applied_for_table += applied
            total_rows += applied

            if not payload.get("hasMore"):
                break
            next_offset = payload.get("nextOffset")
            if next_offset is None or int(next_offset) <= offset:
                raise RuntimeError(
                    f"Baseline pagination stalled for {table_name} at {offset}."
                )
            offset = int(next_offset)

        table_counts[table_name] = applied_for_table
        if applied_for_table:
            logger.info(
                "Baseline merged %s rows from %s.",
                applied_for_table,
                table_name,
            )

    # Only mark baseline complete after every table has committed successfully.
    # Changes created while baseline was running remain > watermark and are read next.
    _save_state(watermark, baseline_complete=True)
    logger.info(
        "Cloud baseline complete at watermark %s: %s rows merged.",
        watermark,
        total_rows,
    )
    return {
        "baseline_rows": total_rows,
        "baseline_tables": table_counts,
        "watermark": watermark,
    }


def sync_once() -> dict:
    _assert_local_database()
    cfg = _load_json(CONFIG_PATH, {})
    if not cfg.get("base_url") or not cfg.get("token"):
        raise RuntimeError("Base PC is not paired. Run: python scripts/pair_render_sync.py")
    state = _load_json(
        STATE_PATH,
        {"last_change_id": 0, "baseline_complete": False},
    )

    baseline_result = None
    if not bool(state.get("baseline_complete")):
        baseline_result = _bootstrap_baseline(cfg["base_url"], cfg["token"])
        state = _load_json(
            STATE_PATH,
            {"last_change_id": 0, "baseline_complete": False},
        )

    cursor = int(state.get("last_change_id", 0) or 0)
    totals = {
        "insert_or_update": 0,
        "delete": 0,
        "skipped": 0,
        "batches": 0,
        "baseline": baseline_result,
    }

    while True:
        payload = _fetch_changes(cfg["base_url"], cfg["token"], cursor)
        changes = payload.get("changes") or []
        if not changes:
            _write_status(
                state="RUNNING",
                last_change_id=cursor,
                last_result=totals,
                message="No new cloud changes.",
            )
            return totals

        result = _apply_batch(changes)
        for key in ("insert_or_update", "delete", "skipped"):
            totals[key] += int(result.get(key, 0))
        totals["batches"] += 1
        cursor = int(payload.get("lastChangeId", cursor))
        _save_state(cursor, baseline_complete=True)
        logger.info(
            "Merged cloud changes through %s: upserts=%s deletes=%s skipped=%s",
            cursor, result["insert_or_update"], result["delete"], result["skipped"],
        )

        if not payload.get("hasMore"):
            _write_status(
                state="RUNNING",
                last_change_id=cursor,
                last_result=totals,
                message="Cloud changes merged successfully.",
            )
            return totals


def main() -> int:
    try:
        result = sync_once()
        print(json.dumps({"ok": True, **result}))
        return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        message = f"HTTP {exc.code}: {body}"
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"

    logger.error("Render -> Base PC sync failed: %s", message)
    _write_status(state="ERROR", error=message)
    print(message)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
