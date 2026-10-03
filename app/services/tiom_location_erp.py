from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Location, WbMovement
from app.site_models import TiomLocationRole, TiomWbCanonical
from app.services.tiom_erp import resolve_location_id, resolve_product_id
from app.services.time_context import now_local


def upsert_location_role(db: Session, location_id: str, role: str, entered_by: str = "SYSTEM"):
    role = str(role or "").strip().upper()
    if role not in {"SOURCE", "DESTINATION"}:
        raise ValueError("Location role must be SOURCE or DESTINATION.")
    key = f"{location_id}:{role}"
    obj = db.get(TiomLocationRole, key)
    if not obj:
        obj = TiomLocationRole(
            role_id=key,
            location_id=location_id,
            role=role,
            active=True,
            entered_by=entered_by,
        )
        db.add(obj)
    else:
        obj.active = True
    return obj


def location_options(db: Session, role: str) -> list[dict]:
    role = str(role or "").strip().upper()
    rows = db.execute(
        select(TiomLocationRole, Location)
        .join(Location, Location.location_id == TiomLocationRole.location_id)
        .where(
            TiomLocationRole.role == role,
            TiomLocationRole.active.is_(True),
            Location.active.is_(True),
        )
        .order_by(Location.location_name, Location.location_id)
    ).all()
    return [
        {
            "id": loc.location_id,
            "label": loc.location_name,
            "type": loc.location_type or "",
        }
        for _, loc in rows
    ]


def canonicalize_wb(db: Session, wb: WbMovement) -> TiomWbCanonical:
    source_id = resolve_location_id(db, wb.source_raw, "SOURCE")
    destination_id = resolve_location_id(db, wb.destination_raw, "DESTINATION")
    material_id = resolve_product_id(db, wb)
    missing = []
    if wb.source_raw and not source_id:
        missing.append("SOURCE")
    if wb.destination_raw and not destination_id:
        missing.append("DESTINATION")
    if (wb.material_code or wb.material_name) and not material_id:
        missing.append("MATERIAL")
    status = "OK" if not missing else "UNMAPPED_" + "_".join(missing)

    row = db.get(TiomWbCanonical, wb.movement_key)
    if not row:
        row = TiomWbCanonical(movement_key=wb.movement_key)
        db.add(row)
    row.source_location_id = source_id
    row.destination_location_id = destination_id
    row.material_id = material_id
    row.mapping_status = status
    row.normalized_at = now_local()
    return row


def canonicalize_wb_rows(db: Session, rows: list[WbMovement]) -> dict[str, TiomWbCanonical]:
    out = {}
    for wb in rows:
        out[wb.movement_key] = canonicalize_wb(db, wb)
    db.flush()
    return out


def backfill_wb_canonical(db: Session) -> dict:
    rows = list(db.scalars(select(WbMovement)))
    mapped = source_missing = destination_missing = material_missing = 0
    for wb in rows:
        c = canonicalize_wb(db, wb)
        if c.mapping_status == "OK":
            mapped += 1
        if wb.source_raw and not c.source_location_id:
            source_missing += 1
        if wb.destination_raw and not c.destination_location_id:
            destination_missing += 1
        if (wb.material_code or wb.material_name) and not c.material_id:
            material_missing += 1
    db.flush()
    return {
        "wbRows": len(rows),
        "mapped": mapped,
        "sourceUnmapped": source_missing,
        "destinationUnmapped": destination_missing,
        "materialUnmapped": material_missing,
    }
