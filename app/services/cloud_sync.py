from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

logger = logging.getLogger("nmtpl.sync")

SYNC_TABLES = (
    "persons", "equipment", "locations", "products", "shift_rotation",
    "shift_master", "activity_master", "person_attendance",
    "equipment_attendance", "shift_crew", "shift_deployment", "shift_state",
    "load_trip", "wb_import_batch", "wb_movement", "load_wb_match",
    "wb_header_alias", "vehicle_alias", "location_alias", "material_alias",
    "hsd_tanker", "hsd_purchase_lot", "hsd_issue", "hsd_issue_allocation",
    "master_options",
    "site", "site_shift", "person_site_assignment", "equipment_site_assignment",
    "site_location", "site_material", "master_import_batch", "master_import_row",
    "site_trip", "site_operational_import_batch", "site_operational_import_row",
    "site_wb_import_batch", "site_wb_movement", "site_weight_factor",
    "site_hsd_transaction", "site_person_attendance", "site_asset_attendance",
    "site_deployment", "site_asset_meter", "site_trip_reconciliation",
    "site_survey_measurement", "site_billing_reconciliation",
    "site_data_quality_issue", "site_satellite_observation",
    "tiom_source_deployment", "tiom_shift_production_report",
    "tiom_shift_production_movement", "tiom_shift_report_baseline",
    "tiom_mis_report", "tiom_mis_trip_row", "tiom_trip_factor",
    "tiom_mis_trip_detail", "tiom_hsd_receipt_detail",
    "tiom_hsd_issue_detail", "tiom_mis_reconciliation",
    "maintenance_breakdown", "maintenance_job_card", "maintenance_service_plan",
    "maintenance_service_history", "maintenance_component_master",
    "equipment_component_schedule", "component_change_history",
    "maintenance_pm_plan", "maintenance_pm_execution",
    "maintenance_def_profile", "maintenance_def_transaction",
    "maintenance_lubricant_usage", "maintenance_spare_usage",
    "maintenance_tyre", "maintenance_tyre_fitment",
    "maintenance_equipment_document",
)

_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def source_enabled() -> bool:
    return os.getenv("NMTPL_SYNC_SOURCE_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def init_sync_source(engine) -> int:
    if not source_enabled():
        logger.info("Render-to-PC sync source is disabled on this instance.")
        return 0

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync_device (
                device_id VARCHAR(80) PRIMARY KEY,
                token_hash VARCHAR(64) UNIQUE NOT NULL,
                device_name VARCHAR(120) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_seen_at TIMESTAMPTZ NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync_change_log (
                change_id BIGSERIAL PRIMARY KEY,
                table_name VARCHAR(120) NOT NULL,
                operation VARCHAR(1) NOT NULL,
                row_data JSONB NOT NULL,
                changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_sync_change_log_changed_at
            ON sync_change_log(changed_at)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_sync_change_log_table_change
            ON sync_change_log(table_name, change_id)
        """))
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION nmtpl_capture_sync_change()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    INSERT INTO sync_change_log(table_name, operation, row_data)
                    VALUES (TG_TABLE_NAME, 'D', to_jsonb(OLD));
                    RETURN OLD;
                ELSIF TG_OP = 'UPDATE' THEN
                    INSERT INTO sync_change_log(table_name, operation, row_data)
                    VALUES (TG_TABLE_NAME, 'U', to_jsonb(NEW));
                    RETURN NEW;
                ELSE
                    INSERT INTO sync_change_log(table_name, operation, row_data)
                    VALUES (TG_TABLE_NAME, 'I', to_jsonb(NEW));
                    RETURN NEW;
                END IF;
            END;
            $$ LANGUAGE plpgsql
        """))

        installed = 0
        for table_name in SYNC_TABLES:
            if not _NAME_RE.fullmatch(table_name):
                continue
            exists = conn.execute(
                text("SELECT to_regclass(:name)"),
                {"name": f"public.{table_name}"},
            ).scalar()
            if not exists:
                continue
            trigger_name = f"trg_nmtpl_sync_{table_name}"[:60]
            conn.execute(text(
                f'DROP TRIGGER IF EXISTS "{trigger_name}" ON "{table_name}"'
            ))
            conn.execute(text(
                f'CREATE TRIGGER "{trigger_name}" '
                f'AFTER INSERT OR UPDATE OR DELETE ON "{table_name}" '
                f'FOR EACH ROW EXECUTE FUNCTION nmtpl_capture_sync_change()'
            ))
            installed += 1

    logger.info(
        "Render-to-PC sync source enabled; change tracking active on %s tables.",
        installed,
    )
    return installed


def create_device(db: Session, device_name: str) -> dict:
    if not source_enabled():
        raise RuntimeError("This server is not configured as a sync source.")
    token = secrets.token_urlsafe(40)
    device_id = str(uuid4())
    db.execute(
        text("""
            INSERT INTO sync_device(device_id, token_hash, device_name)
            VALUES (:device_id, :token_hash, :device_name)
        """),
        {
            "device_id": device_id,
            "token_hash": _digest(token),
            "device_name": (device_name or "NMTPL Base PC")[:120],
        },
    )
    db.commit()
    return {"deviceId": device_id, "token": token}


def validate_device(db: Session, token: str) -> dict | None:
    if not token:
        return None
    row = db.execute(
        text("""
            SELECT device_id, device_name, active
            FROM sync_device
            WHERE token_hash=:token_hash
        """),
        {"token_hash": _digest(token)},
    ).mappings().first()
    if not row or not row["active"]:
        return None
    db.execute(
        text("UPDATE sync_device SET last_seen_at=now() WHERE device_id=:device_id"),
        {"device_id": row["device_id"]},
    )
    db.commit()
    return dict(row)


def read_changes(db: Session, after_id: int, limit: int) -> dict:
    limit = max(1, min(int(limit), 1000))
    after_id = max(0, int(after_id))
    rows = db.execute(
        text("""
            SELECT change_id, table_name, operation, row_data, changed_at
            FROM sync_change_log
            WHERE change_id > :after_id
            ORDER BY change_id
            LIMIT :limit
        """),
        {"after_id": after_id, "limit": limit},
    ).mappings().all()
    payload = [
        {
            "changeId": int(r["change_id"]),
            "table": r["table_name"],
            "operation": r["operation"],
            "row": r["row_data"],
            "changedAt": r["changed_at"],
        }
        for r in rows
    ]
    last_id = payload[-1]["changeId"] if payload else after_id
    return {
        "changes": payload,
        "lastChangeId": last_id,
        "hasMore": len(payload) >= limit,
        "serverTime": datetime.now(timezone.utc),
    }


def latest_change_id(db: Session) -> int:
    return int(db.execute(text(
        "SELECT COALESCE(MAX(change_id), 0) FROM sync_change_log"
    )).scalar() or 0)


def snapshot_manifest(db: Session) -> dict:
    """Return a point-in-time watermark plus FK-safe table order for bootstrap."""
    bind = db.get_bind()
    inspector = inspect(bind)
    existing = [name for name in SYNC_TABLES if inspector.has_table(name)]
    existing_set = set(existing)

    dependencies: dict[str, set[str]] = {name: set() for name in existing}
    for table_name in existing:
        for fk in inspector.get_foreign_keys(table_name):
            parent = fk.get("referred_table")
            if parent in existing_set and parent != table_name:
                dependencies[table_name].add(parent)

    ordered: list[str] = []
    remaining = {name: set(deps) for name, deps in dependencies.items()}
    while remaining:
        ready = [name for name in existing if name in remaining and not remaining[name]]
        if not ready:
            # Defensive fallback for any schema cycle: preserve the declared stable
            # order. Most TIOM business tables are acyclic; this prevents a hang.
            ordered.extend(name for name in existing if name in remaining)
            break
        for name in ready:
            ordered.append(name)
            remaining.pop(name, None)
        for deps in remaining.values():
            deps.difference_update(ready)

    return {
        "watermark": latest_change_id(db),
        "tables": ordered,
        "dependencies": {
            name: sorted(dependencies[name])
            for name in ordered
        },
    }


def read_snapshot_table(
    db: Session,
    table_name: str,
    offset: int,
    limit: int,
) -> dict:
    """Read current rows for one allowlisted table in deterministic PK order."""
    if table_name not in SYNC_TABLES or not _NAME_RE.fullmatch(table_name):
        raise ValueError("Table is not available for synchronization.")

    bind = db.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(table_name):
        return {
            "table": table_name,
            "rows": [],
            "offset": max(0, int(offset)),
            "nextOffset": None,
            "hasMore": False,
        }

    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    pk = inspector.get_pk_constraint(table_name).get("constrained_columns") or []

    # Names originate from SQLAlchemy inspection and table_name is also allowlisted.
    order_sql = ", ".join(f'"{name}"' for name in pk) if pk else "ctid"
    rows = db.execute(
        text(
            f'SELECT to_jsonb(t) AS row '
            f'FROM "{table_name}" AS t '
            f'ORDER BY {order_sql} LIMIT :limit OFFSET :offset'
        ),
        {"limit": limit, "offset": offset},
    ).scalars().all()

    has_more = len(rows) >= limit
    return {
        "table": table_name,
        "rows": rows,
        "offset": offset,
        "nextOffset": offset + len(rows) if has_more else None,
        "hasMore": has_more,
    }
