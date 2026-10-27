from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from sqlalchemy import Date, DateTime, MetaData, Numeric, Table, Time, delete, inspect, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.services.cloud_sync import SYNC_TABLES, latest_change_id

class SyncConflict(Exception):
    pass


def _coerce(column, value):
    if value is None:
        return None
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    if isinstance(column.type, Date) and not isinstance(column.type, DateTime) and isinstance(value, str):
        return date.fromisoformat(value[:10])
    if isinstance(column.type, Time) and isinstance(value, str):
        return time.fromisoformat(value)
    if isinstance(column.type, Numeric) and not isinstance(value, Decimal):
        return Decimal(str(value))
    return value


def receive(db, device_id: str, base: int, entries: list[dict], initial: int = 0) -> dict:
    if not 1 <= len(entries) <= 100 or base < 0 or initial < 0:
        raise ValueError('Invalid upload batch.')
    conn = db.connection()
    conn.execute(text('''CREATE TABLE IF NOT EXISTS sync_upload_cursor (
        device_id VARCHAR(80) PRIMARY KEY REFERENCES sync_device(device_id),
        last_local_id BIGINT NOT NULL DEFAULT 0)'''))
    conn.execute(text('INSERT INTO sync_upload_cursor(device_id, last_local_id) VALUES (:id, :initial) ON CONFLICT DO NOTHING'),
                 {'id': device_id, 'initial': initial})
    cursor = int(conn.execute(text('SELECT last_local_id FROM sync_upload_cursor WHERE device_id=:id FOR UPDATE'), {'id': device_id}).scalar())
    if base > latest_change_id(db):
        raise ValueError('PC watermark exceeds Render watermark.')
    schema = MetaData()
    tables = {}
    inspector = inspect(conn)
    applied = 0
    for entry in entries:
        number = int(entry.get('changeId', -1))
        if number <= cursor:
            continue
        if number != cursor + 1:
            raise ValueError('Upload sequence gap.')
        name = entry.get('table')
        op = entry.get('operation')
        raw = entry.get('row')
        if name not in SYNC_TABLES or not inspector.has_table(name) or op not in ('I', 'U', 'D') or not isinstance(raw, dict):
            raise ValueError('Invalid upload table, operation or row.')
        if name not in tables:
            tables[name] = Table(name, schema, autoload_with=conn)
        table = tables[name]
        pk = [c.name for c in table.primary_key.columns]
        if not pk or any(k not in raw for k in pk) or any(k not in table.c for k in raw):
            raise ValueError('Unknown column or missing primary key.')
        row = {k: _coerce(table.c[k], v) for k, v in raw.items()}
        predicates = [table.c[k] == row[k] for k in pk]
        # Existing row lock prevents edits crossing the conflict check and write.
        conn.execute(table.select().with_only_columns(*[table.c[k] for k in pk]).where(*predicates).with_for_update()).first()
        recent = conn.execute(text('''SELECT row_data FROM sync_change_log
            WHERE change_id > :base AND table_name=:name
            AND (origin_device IS NULL OR origin_device <> :device)'''),
            {'base': base, 'name': name, 'device': device_id}).scalars()
        if any(all(str(event.get(k)) == str(raw[k]) for k in pk) for event in recent):
            raise SyncConflict(f'{name} was changed on Render after the PC last pulled; no rows were uploaded.')
        conn.execute(text("SELECT set_config('nmtpl.sync_device', :id, true)"), {'id': device_id})
        if op == 'D':
            conn.execute(delete(table).where(*predicates))
        else:
            statement = pg_insert(table).values(**row)
            updates = {k: getattr(statement.excluded, k) for k in row if k not in pk}
            if name == 'site_asset_meter':
                existing = conn.execute(table.select().with_only_columns(table.c.reading_id).where(*predicates)).first()
                if not existing:
                    natural = ['site_id', 'operating_date', 'shift', 'asset_id', 'meter_type']
                    statement = statement.on_conflict_do_update(constraint='uq_site_asset_meter',
                        set_={k: getattr(statement.excluded, k) for k in row if k not in natural})
                    conn.execute(statement)
                    cursor = number
                    applied += 1
                    continue
            if updates:
                statement = statement.on_conflict_do_update(index_elements=[table.c[k] for k in pk], set_=updates)
            else:
                statement = statement.on_conflict_do_nothing(index_elements=[table.c[k] for k in pk])
            conn.execute(statement)
        cursor = number
        applied += 1
    conn.execute(text('UPDATE sync_upload_cursor SET last_local_id=:n WHERE device_id=:id'), {'n': cursor, 'id': device_id})
    db.commit()
    return {'ok': True, 'lastLocalId': cursor, 'applied': applied}
