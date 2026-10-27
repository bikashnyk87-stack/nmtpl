"""Regression: late Despatch tables must backfill without resetting WB sync state."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from scripts import pull_render_sync as sync


def test_missing_despatch_schema_created_only_once(tmp_path, monkeypatch):
    e = create_engine("sqlite:///" + str(tmp_path / "local.db"))
    monkeypatch.setattr(sync, "engine", e)
    monkeypatch.setattr(sync, "_assert_local_database", lambda: None)
    import app.services.cloud_sync as cloud
    installs = []
    monkeypatch.setattr(cloud, "init_sync_source",
                        lambda engine, force_local=False: installs.append(force_local))
    missing = sync._ensure_despatch_local_schema()
    assert set(missing) == set(sync.DESPATCH_MIRROR_TABLES)
    assert installs == [True]
    assert sync._ensure_despatch_local_schema() == []
    with e.connect() as conn:
        assert int(conn.execute(text("SELECT COUNT(*) FROM tiom_despatch_trip")).scalar()) == 0
    e.dispose()


def test_backfill_reconciles_late_tables_without_modifying_wb_cursor(tmp_path, monkeypatch):
    e = create_engine("sqlite:///" + str(tmp_path / "replica.db"))
    from app.db import Base
    from app.routers.tiom_despatch import DespatchSender, DespatchTrip, DespatchPermitDay, DespatchAudit
    Base.metadata.create_all(e, tables=[x.__table__ for x in
                             (DespatchSender, DespatchTrip, DespatchPermitDay, DespatchAudit)])
    monkeypatch.setattr(sync, "engine", e)
    monkeypatch.setattr(sync, "_assert_local_database", lambda: None)
    monkeypatch.setattr(sync, "DESPATCH_BACKFILL_PATH", tmp_path / "despatch_state.json")
    existing_cursor = tmp_path / "old_wb_cursor.json"
    existing_cursor.write_text('{"last_change_id": 48774, "baseline_complete": true}')
    fake_remote = {"tiom_despatch_sender": [
        {"email": "allowed@example.com", "name": "Valid", "active": True}
    ], "tiom_despatch_trip": [
        {"epass_no": "T1", "report_date": "2026-10-26", "permit_no": "P1",
         "net_mt": 30, "tare_mt": 15, "gross_mt": 45, "status": "ACTIVE"}
    ], "tiom_despatch_permit_day": [], "tiom_despatch_audit": []}
    seen = []
    def manifest(base, token):
        return {"tables": list(sync.DESPATCH_MIRROR_TABLES),
                "despatchRowCounts": {t: len(fake_remote[t]) for t in sync.DESPATCH_MIRROR_TABLES}}
    def snapshot(base, token, table, offset, limit):
        seen.append((table,offset))
        rows = fake_remote[table][offset:offset+limit]
        return {"rows": rows, "hasMore": False, "nextOffset": None}
    def apply(table, rows):
        with e.begin() as conn:
            for row in rows:
                # Fixture contains a single row per primary key; avoid PostgreSQL
                # upsert in the SQLite-only behavioral unit test.
                pk = "email" if table == "tiom_despatch_sender" else "epass_no"
                conn.execute(text(f'DELETE FROM "{table}" WHERE "{pk}" = :key'),
                             {"key": row[pk]})
                from sqlalchemy import MetaData, Table
                tbl = Table(table, MetaData(), autoload_with=conn)
                conn.execute(tbl.insert().values(**row))
        return len(rows)
    monkeypatch.setattr(sync, "_fetch_snapshot_manifest", manifest)
    monkeypatch.setattr(sync, "_fetch_snapshot_table", snapshot)
    monkeypatch.setattr(sync, "_apply_snapshot_rows", apply)
    first = sync._repair_despatch_baseline("https://render.test", "token")
    assert first["complete"] is True
    assert first["verified_local_counts"]["tiom_despatch_trip"] == 1
    assert existing_cursor.read_text() == '{"last_change_id": 48774, "baseline_complete": true}'
    count_scans = len(seen)
    second = sync._repair_despatch_baseline("https://render.test", "token")
    assert second["complete"] is True
    assert len(seen) == count_scans
    # If a table is emptied after the baseline, the next normal poll restores it.
    with e.begin() as conn:
        conn.execute(text("DELETE FROM tiom_despatch_trip"))
    third = sync._repair_despatch_baseline("https://render.test", "token")
    assert third["verified_local_counts"]["tiom_despatch_trip"] == 1
    assert len(seen) == count_scans + 1
    e.dispose()
