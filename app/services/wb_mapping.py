from __future__ import annotations

import re
from datetime import timedelta
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Location, LocationAlias, WbHeaderAlias


CANONICAL_FIELDS = (
    "move", "date", "shift", "vehicle", "matcode", "matname",
    "source_code", "source_name", "dest_code", "dest_name",
    "tare", "gross", "net", "time",
)

DEFAULT_HEADER_ALIASES = (
    ("move", "Movement No", 1, 10, False),
    ("move", "Movement Number", 1, 20, False),
    ("date", "Movement Date", 1, 10, True),
    ("date", "Date", 1, 50, True),
    ("shift", "Shift Code", 1, 10, True),
    ("shift", "Shift", 1, 50, True),
    ("vehicle", "Vehicle Number", 1, 10, True),
    ("vehicle", "Vehicle No", 1, 20, True),
    ("vehicle", "Vehicle Regd No", 1, 30, True),
    ("matcode", "Material Number", 1, 10, False),
    ("matcode", "Material Code", 1, 20, False),
    ("matname", "Material Description", 1, 10, False),
    ("matname", "Material", 1, 30, False),

    # Stable IDs/codes always win over descriptive names.
    ("source_code", "Source Location Id", 1, 5, False),
    ("source_code", "Source Location ID", 1, 5, False),
    ("source_code", "Source ID", 1, 10, False),
    ("source_code", "Source Location", 1, 20, False),
    ("source_name", "Source Location Name", 1, 5, False),
    ("source_name", "Source Name", 1, 10, False),

    ("dest_code", "Destination Location Id", 1, 5, False),
    ("dest_code", "Destination Location ID", 1, 5, False),
    ("dest_code", "Destination ID", 1, 10, False),
    # TIOM current workbook contains the same header twice:
    # first occurrence is the destination code, second is the descriptive name.
    ("dest_code", "Destination Location", 1, 20, False),
    ("dest_name", "Destination Location Name", 1, 5, False),
    ("dest_name", "Destination Name", 1, 10, False),
    ("dest_name", "Destination Location", 2, 20, False),

    ("tare", "Tare Weight", 1, 10, False),
    ("tare", "Tare Wt", 1, 20, False),
    ("gross", "Gross Weight", 1, 10, True),
    ("gross", "Gross Wt", 1, 20, True),
    ("net", "Net Weight", 1, 10, False),
    ("net", "Net Wt", 1, 20, False),
    ("time", "GW Created Time", 1, 10, True),
    ("time", "Gross Weight Time", 1, 20, True),
    ("time", "Gross Time", 1, 30, True),
)


def norm_header(value) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def norm_location(value) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def norm_vehicle(value) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def ensure_wb_header_mapping(db: Session) -> None:
    """Create/seed the additive mapping table without modifying existing transaction tables."""
    WbHeaderAlias.__table__.create(bind=db.get_bind(), checkfirst=True)
    existing = {
        (r.canonical_field, r.header_alias, int(r.occurrence or 1))
        for r in db.scalars(select(WbHeaderAlias)).all()
    }
    changed = False
    for field, alias, occurrence, priority, required in DEFAULT_HEADER_ALIASES:
        key = (field, alias, occurrence)
        if key in existing:
            continue
        db.add(WbHeaderAlias(
            canonical_field=field,
            header_alias=alias,
            occurrence=occurrence,
            priority=priority,
            required=required,
            active=True,
        ))
        changed = True
    if changed:
        db.flush()


def _positions(header_values: Iterable[object]) -> dict[str, list[int]]:
    positions: dict[str, list[int]] = {}
    for idx, value in enumerate(header_values):
        if str(value or "").strip():
            positions.setdefault(norm_header(value), []).append(idx)
    return positions


def resolve_columns(db: Session, header_values: Iterable[object]) -> tuple[dict[str, int | None], dict]:
    ensure_wb_header_mapping(db)
    values = list(header_values)
    positions = _positions(values)
    mappings = list(db.scalars(
        select(WbHeaderAlias)
        .where(WbHeaderAlias.active)
        .order_by(WbHeaderAlias.canonical_field, WbHeaderAlias.priority, WbHeaderAlias.id)
    ))
    resolved: dict[str, int | None] = {field: None for field in CANONICAL_FIELDS}
    matched = {}
    required_fields = set()

    for mapping in mappings:
        field = mapping.canonical_field
        if field not in resolved:
            continue
        if mapping.required:
            required_fields.add(field)
        if resolved[field] is not None:
            continue
        indexes = positions.get(norm_header(mapping.header_alias), [])
        occurrence = max(1, int(mapping.occurrence or 1))
        if len(indexes) >= occurrence:
            idx = indexes[occurrence - 1]
            resolved[field] = idx
            matched[field] = {
                "header": values[idx],
                "index": idx,
                "occurrence": occurrence,
                "mappingId": mapping.id,
            }

    # Net can be derived from Gross - Tare. Do not force Net if Gross is present.
    missing = sorted(
        f for f in required_fields
        if resolved.get(f) is None and not (f == "gross" and resolved.get("net") is not None)
    )
    duplicate_headers = {
        key: idxs for key, idxs in positions.items() if len(idxs) > 1
    }
    return resolved, {
        "matched": matched,
        "missing": missing,
        "duplicates": duplicate_headers,
        "headers": [str(x or "") for x in values],
    }


def find_wb_sheet(workbook, db: Session):
    """Find the actual transaction sheet, even when a pivot/summary sheet is first/active."""
    ensure_wb_header_mapping(db)
    best = None
    for ws in workbook.worksheets:
        for row_no, row in enumerate(
            ws.iter_rows(min_row=1, max_row=min(ws.max_row, 25), values_only=True), 1
        ):
            columns, diag = resolve_columns(db, row)
            score = sum(columns.get(k) is not None for k in ("date", "shift", "vehicle", "gross", "net", "time"))
            if columns.get("vehicle") is not None and (columns.get("gross") is not None or columns.get("net") is not None):
                if best is None or score > best[0]:
                    best = (score, ws, row_no, columns, diag)
                if score >= 6 and not diag["missing"]:
                    return ws, row_no, columns, diag
    if best:
        _, ws, row_no, columns, diag = best
        if diag["missing"]:
            raise ValueError(
                "WB required header mapping missing: " + ", ".join(diag["missing"]) +
                ". Add the new header in Masters > WB Header Mapping."
            )
        return ws, row_no, columns, diag
    raise ValueError(
        "WB transaction sheet/header row not found. Configure its header aliases in Masters > WB Header Mapping."
    )


def row_value(row, columns: dict[str, int | None], field: str):
    idx = columns.get(field)
    return row[idx] if idx is not None and idx < len(row) else None


def clock_in_shift(definition, clock) -> bool:
    """Return True when a clock time belongs to the configured shift window."""
    if clock is None or definition is None:
        return False
    start, end = definition.start_time, definition.end_time
    if end > start:
        return start <= clock < end
    return clock >= start or clock < end


def expected_movement_date(operating_date, clock, definition):
    """Calendar date expected in WB for an operating date/shift/time.

    For an overnight shift, post-midnight movements occur on operating_date + 1
    but remain part of the previous operating date.
    """
    if operating_date is None or not clock_in_shift(definition, clock):
        return None
    if definition.end_time <= definition.start_time and clock < definition.end_time:
        return operating_date + timedelta(days=1)
    return operating_date


def operating_date_from_movement(movement_date, clock, definition):
    """Convert WB calendar Movement Date into the NMTPL operating date."""
    if movement_date is None or not clock_in_shift(definition, clock):
        return None
    if definition.end_time <= definition.start_time and clock < definition.end_time:
        return movement_date - timedelta(days=1)
    return movement_date


@dataclass
class LocationResolver:
    direct: dict[str, str]
    source_alias: dict[str, str]
    destination_alias: dict[str, str]
    any_alias: dict[str, str]

    def resolve(self, code, name, direction: str) -> str:
        direction = str(direction or "ANY").upper()
        for raw in (code, name):
            text = str(raw or "").strip()
            if not text:
                continue
            key = norm_location(text)
            if direction == "SOURCE" and key in self.source_alias:
                return self.source_alias[key]
            if direction == "DESTINATION" and key in self.destination_alias:
                return self.destination_alias[key]
            if key in self.any_alias:
                return self.any_alias[key]
            if key in self.direct:
                return self.direct[key]
        # Prefer the stable code; fall back to descriptive name.
        return str(code or name or "").strip()

    def resolve_raw(self, raw, direction: str) -> str:
        return self.resolve(raw, None, direction)


def build_location_resolver(db: Session) -> LocationResolver:
    direct: dict[str, str] = {}
    for row in db.scalars(select(Location)).all():
        direct[norm_location(row.location_id)] = row.location_id
        if row.location_name:
            direct.setdefault(norm_location(row.location_name), row.location_id)

    source_alias, destination_alias, any_alias = {}, {}, {}
    for alias in db.scalars(select(LocationAlias).where(LocationAlias.active)).all():
        key = norm_location(alias.alias)
        direction = str(alias.direction or "ANY").upper()
        if direction == "SOURCE":
            source_alias[key] = alias.location_id
        elif direction == "DESTINATION":
            destination_alias[key] = alias.location_id
        else:
            any_alias[key] = alias.location_id
    return LocationResolver(direct, source_alias, destination_alias, any_alias)
