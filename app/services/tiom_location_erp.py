from __future__ import annotations

import hashlib
import re

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import Location, LocationAlias, WbMovement
from app.site_models import TiomLocationRole, TiomWbCanonical
from app.services.tiom_erp import resolve_product_id
from app.services.wb_mapping import build_location_resolver
from app.services.time_context import now_local

LOCATION_ROLES = {"SOURCE", "DESTINATION", "BOTH", "UNCLASSIFIED"}


def ensure_location_master_schema(engine: Engine) -> None:
    """Add the centralized Location.role column to older PC/temp databases."""
    with engine.begin() as conn:
        cols = {str(c["name"]).lower() for c in inspect(conn).get_columns("locations")}
        if "role" not in cols:
            conn.execute(text("ALTER TABLE locations ADD COLUMN role VARCHAR(20)"))


def _merge_role(current: str | None, incoming: str | None) -> str:
    current = str(current or "").strip().upper()
    incoming = str(incoming or "").strip().upper()
    if incoming not in {"SOURCE", "DESTINATION", "BOTH"}:
        return current if current in LOCATION_ROLES else "UNCLASSIFIED"
    if current in {"", "ANY", "UNCLASSIFIED"}:
        return incoming
    if current == incoming or current == "BOTH":
        return current
    return "BOTH"


def ensure_location_master_roles(db: Session) -> None:
    """Migrate old hidden TIOM roles/aliases into the central Location Master."""
    locations = {x.location_id: x for x in db.scalars(select(Location))}
    changed = False

    # Old temp-server compatibility only. New logic never writes this table.
    for row in db.scalars(select(TiomLocationRole).where(TiomLocationRole.active.is_(True))):
        loc = locations.get(row.location_id)
        if loc:
            merged = _merge_role(loc.role, row.role)
            if loc.role != merged:
                loc.role = merged
                changed = True

    # Direction-specific aliases are evidence. ANY is only an alias-matching
    # rule and must not classify the canonical Location as BOTH.
    for alias in db.scalars(select(LocationAlias).where(LocationAlias.active.is_(True))):
        loc = locations.get(alias.location_id)
        if not loc:
            continue
        direction = str(alias.direction or "").upper()
        if direction in {"SOURCE", "DESTINATION"}:
            merged = _merge_role(loc.role, direction)
            if loc.role != merged:
                loc.role = merged
                changed = True

    # Canonical WB history is authoritative evidence of how the location was used.
    for row in db.scalars(select(TiomWbCanonical)):
        if row.source_location_id and row.source_location_id in locations:
            loc = locations[row.source_location_id]
            merged = _merge_role(loc.role, "SOURCE")
            if loc.role != merged:
                loc.role = merged
                changed = True
        if row.destination_location_id and row.destination_location_id in locations:
            loc = locations[row.destination_location_id]
            merged = _merge_role(loc.role, "DESTINATION")
            if loc.role != merged:
                loc.role = merged
                changed = True

    for loc in locations.values():
        role = str(loc.role or "").upper()
        if role not in LOCATION_ROLES:
            loc.role = "UNCLASSIFIED"
            changed = True
    if changed:
        db.flush()


def upsert_location_role(db: Session, location_id: str, role: str, entered_by: str = "SYSTEM"):
    """Compatibility API: update the central Location Master, not a parallel role table."""
    loc = db.get(Location, location_id)
    if not loc:
        raise ValueError(f"Unknown Location Master record: {location_id}")
    role = str(role or "").strip().upper()
    if role not in {"SOURCE", "DESTINATION", "BOTH"}:
        raise ValueError("Location role must be SOURCE, DESTINATION or BOTH.")
    loc.role = _merge_role(loc.role, role)
    db.flush()
    return loc


def location_options(db: Session, role: str) -> list[dict]:
    ensure_location_master_roles(db)
    role = str(role or "").strip().upper()
    if role not in {"SOURCE", "DESTINATION"}:
        raise ValueError("Location role must be SOURCE or DESTINATION.")
    rows = list(db.scalars(
        select(Location)
        .where(
            Location.active.is_(True),
            Location.role.in_([role, "BOTH"]),
        )
        .order_by(Location.location_name, Location.location_id)
    ))
    return [
        {
            "id": loc.location_id,
            "label": loc.location_name,
            "type": loc.location_type or "",
            "role": loc.role or "UNCLASSIFIED",
        }
        for loc in rows
    ]


def _new_location_id(db: Session, raw: str) -> str:
    raw = str(raw or "").strip()
    base = re.sub(r"[^A-Z0-9]+", "-", raw.upper()).strip("-")[:70] or "WB-LOCATION"
    candidate = base
    existing = db.get(Location, candidate)
    if not existing:
        return candidate
    if existing.location_name.strip().upper() == raw.upper():
        return candidate
    suffix = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:7].upper()
    return f"{base[:72]}-{suffix}"[:80]


def _ensure_alias(db: Session, raw: str, location_id: str, direction: str) -> None:
    raw = str(raw or "").strip()
    if not raw:
        return

    # Session.get() cannot see a newly-added alias until it has been flushed.
    # A WB batch can legitimately use the same raw location as both SOURCE and
    # DESTINATION, so check pending objects first to avoid two inserts with the
    # same primary-key alias in one transaction.
    alias = next(
        (
            row for row in db.new
            if isinstance(row, LocationAlias) and row.alias == raw
        ),
        None,
    )
    if alias is None:
        alias = db.get(LocationAlias, raw)

    if alias is None:
        db.add(LocationAlias(
            alias=raw,
            location_id=location_id,
            direction=direction,
            active=True,
        ))
        return

    # One alias maps to one canonical Location. If the same canonical location
    # is observed in both directions, make the alias direction-neutral. The
    # central Location.role holds SOURCE / DESTINATION / BOTH.
    if alias.location_id != location_id:
        return

    old = str(alias.direction or "ANY").upper()
    incoming = str(direction or "ANY").upper()
    if old != incoming and old != "ANY":
        alias.direction = "ANY"
    alias.active = True


def ensure_wb_location(db: Session, raw: str, role: str, resolver=None) -> str | None:
    """Resolve or auto-create a canonical Location Master from WB data."""
    raw = str(raw or "").strip()
    if not raw:
        return None
    role = str(role or "").strip().upper()
    if role not in {"SOURCE", "DESTINATION"}:
        raise ValueError("WB location role must be SOURCE or DESTINATION.")

    resolver = resolver or build_location_resolver(db)
    candidate = resolver.resolve_raw(raw, role)
    loc = db.get(Location, candidate) if candidate else None
    if not loc:
        location_id = _new_location_id(db, raw)
        loc = db.get(Location, location_id)
        if not loc:
            loc = Location(
                location_id=location_id,
                location_name=raw,
                location_type="WB_AUTO",
                role=role,
                active=True,
            )
            db.add(loc)
            db.flush()
        else:
            loc.role = _merge_role(loc.role, role)
            loc.active = True
    else:
        loc.role = _merge_role(loc.role, role)
        loc.active = True

    _ensure_alias(db, raw, loc.location_id, role)
    return loc.location_id


def canonicalize_wb(
    db: Session,
    wb: WbMovement,
    *,
    resolver=None,
    source_cache: dict | None = None,
    destination_cache: dict | None = None,
    material_cache: dict | None = None,
) -> TiomWbCanonical:
    resolver = resolver or build_location_resolver(db)
    source_cache = source_cache if source_cache is not None else {}
    destination_cache = destination_cache if destination_cache is not None else {}
    material_cache = material_cache if material_cache is not None else {}

    source_key = str(wb.source_raw or "")
    destination_key = str(wb.destination_raw or "")
    material_key = (str(wb.material_code or ""), str(wb.material_name or ""))

    if source_key not in source_cache:
        source_cache[source_key] = ensure_wb_location(db, wb.source_raw, "SOURCE", resolver) if wb.source_raw else None
    if destination_key not in destination_cache:
        destination_cache[destination_key] = ensure_wb_location(db, wb.destination_raw, "DESTINATION", resolver) if wb.destination_raw else None
    if material_key not in material_cache:
        material_cache[material_key] = resolve_product_id(db, wb)

    source_id = source_cache[source_key]
    destination_id = destination_cache[destination_key]
    material_id = material_cache[material_key]
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
    ensure_location_master_roles(db)
    resolver = build_location_resolver(db)
    source_cache: dict[str, str | None] = {}
    destination_cache: dict[str, str | None] = {}
    material_cache: dict[tuple[str, str], str | None] = {}
    for wb in rows:
        out[wb.movement_key] = canonicalize_wb(
            db, wb,
            resolver=resolver,
            source_cache=source_cache,
            destination_cache=destination_cache,
            material_cache=material_cache,
        )
    db.flush()
    return out


def backfill_wb_canonical(db: Session) -> dict:
    rows = list(db.scalars(select(WbMovement)))
    ensure_location_master_roles(db)
    resolver = build_location_resolver(db)
    source_cache: dict[str, str | None] = {}
    destination_cache: dict[str, str | None] = {}
    material_cache: dict[tuple[str, str], str | None] = {}
    mapped = source_missing = destination_missing = material_missing = 0
    for wb in rows:
        c = canonicalize_wb(
            db, wb,
            resolver=resolver,
            source_cache=source_cache,
            destination_cache=destination_cache,
            material_cache=material_cache,
        )
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
