"""KOCP MIS source registers: Coal aggregated shift sheets and OB individual cards.

No source photograph or individual trip timestamps are collected. Verification
writes to the existing SiteTrip and SiteAssetMeter engines exactly once.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.auth import csrf, get_user
from app.db import get_db
from app.models import Equipment, Person
from app.site_auth import has_permission, require_site
from app.site_models import (
    SiteShift, SiteLocation, SiteMaterial, SiteMovementRoute, SiteAssetMeter,
    SiteTrip, SiteWeightFactor, SiteBillingReconciliation, SiteOperationalCode,
    SiteShiftTripCard, SiteShiftTripCardLine, PersonSiteAssignment,
)
from app.routers.site_ops import (
    _audit, _site_person_or_422, _site_equipment_or_422, _site_shift_or_422,
    _site_location_or_422
)
from app.services.kocp_factor_rules import resolve_kocp_point_factor
from app.services.kocp_report_formats import build as build_kocp_management_report
from app.services.kocp_equipment import kocp_asset_allowed, kocp_equipment_category, kocp_role_allowed

router = APIRouter(prefix="/api/KOCP/shift-register", tags=["KOCP shift production register"])
KINDS = {"COAL", "OB"}
CODE_KINDS = {"RELAY", "PATCH", "UNLOAD_POINT"}


def _txt(value, maximum=120):
    value = " ".join(str(value or "").strip().split())
    if len(value) > maximum:
        raise HTTPException(422, "Field length exceeds allowed maximum.")
    return value


def _source_code(value):
    return _txt(value, 45).upper()


def _date(value):
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        raise HTTPException(422, "Enter a valid operating date.")


def _auth(db, request, module="TRIP", action="VIEW", mutate=False):
    if mutate:
        csrf(request)
    user = get_user(db, request)
    require_site(db, user, "KOCP")
    allowed = user.admin or has_permission(db, user, "KOCP", module, action)
    if module == "TRIP" and action == "VIEW" and not allowed:
        allowed = any(has_permission(db,user,"KOCP","TRIP",verb) for verb in ("CREATE","EDIT","APPROVE"))
    if not allowed:
        raise HTTPException(403, f"{module} {action} permission required.")
    return user


def validate_meter_pair(opening, closing):
    if opening in (None, "") and closing in (None, ""):
        return None, None
    if opening in (None, "") or closing in (None, ""):
        raise HTTPException(422, "Both opening and closing meter readings are required together.")
    try:
        a, b = Decimal(str(opening)), Decimal(str(closing))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(422, "Meter readings must be valid numbers.")
    if not a.is_finite() or not b.is_finite() or a < 0 or b < a:
        raise HTTPException(422, "Meter closing reading must be at least opening; neither may be negative.")
    return str(opening), str(closing)


def validate_register_lines(kind, lines):
    kind = _source_code(kind)
    if kind not in KINDS:
        raise HTTPException(422, "Choose Coal or OB.")
    if not isinstance(lines, list) or not (1 <= len(lines) <= 200):
        raise HTTPException(422, "Enter between 1 and 200 source rows.")
    normalized, seen = [], set()
    for index, raw in enumerate(lines, 1):
        if not isinstance(raw, dict):
            raise HTTPException(422, f"Source row {index} must be an object.")
        try:
            number = int(raw.get("lineNo", index))
        except (TypeError, ValueError):
            raise HTTPException(422, f"Invalid source row number at line {index}.")
        if number < 1 or number in seen:
            raise HTTPException(422, "Source line numbers must be positive and unique.")
        seen.add(number)
        if kind == "COAL":
            vehicle, driver = _txt(raw.get("vehicleId"), 50), _txt(raw.get("driverId"), 50)
            value = raw.get("tripCount")
            if isinstance(value, bool) or not str(value or "").isdigit():
                raise HTTPException(422, f"Coal line {number}: enter a positive whole trip count.")
            count = int(value)
            if not (1 <= count <= 200):
                raise HTTPException(422, f"Coal line {number}: trip count must be 1–200.")
            if not vehicle:
                raise HTTPException(422, f"Coal line {number}: vehicle is required.")
            normalized.append({"lineNo": number, "vehicleId": vehicle,
                               "driverId": driver, "tripCount": count,
                               "routeId": _txt(raw.get("routeId"), 80)})
        else:
            excavator = _txt(raw.get("excavatorId"), 50)
            patch = _source_code(raw.get("patchCode"))
            point = _source_code(raw.get("pointCode"))
            source_id = _txt(raw.get("sourceLocationId"), 80)
            destination_id = _txt(raw.get("destinationLocationId"), 80)
            count = str(raw.get("tripCount", 1)).lstrip("0")
            if not (1 <= len(count) <= 3 and count.isascii() and count.isdecimal() and int(count) <= 200):
                raise HTTPException(422, f"OB line {number}: enter a whole trip count from 1 to 200.")
            if not (excavator and (patch or source_id) and (point or destination_id)):
                raise HTTPException(422, f"OB line {number}: excavator, patch and unloading point are required.")
            normalized.append({"lineNo": number, "excavatorId": excavator,
                               "patchCode": patch, "pointCode": point,
                               "sourceLocationId": source_id, "destinationLocationId": destination_id,
                               "tripCount": int(count),
                               "routeId": _txt(raw.get("routeId"), 80)})
    return normalized


def source_trip_total(lines):
    return sum(int(row["tripCount"]) for row in lines)


def _code(db, kind, value, *, required=True):
    code = _source_code(value)
    if not code:
        if required:
            raise HTTPException(422, f"Select {kind} from Masters.")
        return None
    row = db.get(SiteOperationalCode, f"KOCP:{kind}:{code}")
    if not row or not row.active or row.site_id != "KOCP":
        raise HTTPException(422, f"{kind} {code} is not mapped in active KOCP Masters.")
    return row


def _material(db, material_id, kind):
    row = db.get(SiteMaterial, material_id) if material_id else None
    if not row or row.site_id != "KOCP" or not row.active:
        raise HTTPException(422, "Select an active material from KOCP Masters.")
    is_ob = str(row.default_unit or "").upper() in {"CUM", "M3", "M³"}
    if is_ob != (kind == "OB"):
        raise HTTPException(422, "Material unit does not match the Coal/OB register.")
    return row


def _route(db, route_id, kind, *, required=True):
    row = db.get(SiteMovementRoute, route_id) if route_id else None
    if not row or not row.active or row.site_id != "KOCP" or row.movement_kind != kind:
        if not required and not route_id:
            return None
        raise HTTPException(422, f"Choose an active {kind} Route from Masters.")
    _site_location_or_422(db, "KOCP", row.destination_location_id)
    if row.source_location_id:
        _site_location_or_422(db, "KOCP", row.source_location_id)
    return row


def _ob_locations(db, route, line_no, patch_value, unload_value, source_id=None, destination_id=None):
    patch = _code(db, "PATCH", patch_value) if patch_value else None
    unload = _code(db, "UNLOAD_POINT", unload_value) if unload_value else None
    resolved = []
    for label, code, location_id, expected in (
        ("Loading patch", patch, source_id, route.source_location_id if route else None),
        ("Unloading point", unload, destination_id, route.destination_location_id if route else None),
    ):
        if code:
            if not code.parent_location_id or (location_id and code.parent_location_id != location_id):
                raise HTTPException(422, f"OB line {line_no}: {label} code mapping changed or is missing.")
            location_id = code.parent_location_id
        if not location_id or (route and location_id != expected):
            raise HTTPException(422, f"OB line {line_no}: {label} does not match the selected route.")
        _site_location_or_422(db, "KOCP", location_id)
        resolved.append(location_id)
    return patch, unload, *resolved


def _driver_role(role):
    value = str(role or "").strip().upper()
    if "HELPER" in value.split():
        return False
    return "DRIVER" in value.split() or any(
        label in value for label in ("TIPPER OPERATOR", "DUMPER OPERATOR", "TRUCK OPERATOR")
    )


def _driver(db, employee_id, operating_day):
    person = _site_person_or_422(db, "KOCP", employee_id, operating_day)
    if not _driver_role(person.role):
        raise HTTPException(422, "Select an eligible driver from KOCP Employee Master.")
    return person


def _asset(db, machine_id, operating_day, activity, role):
    equipment = _site_equipment_or_422(db, "KOCP", machine_id, operating_day, role.lower() + " equipment")
    if not (kocp_asset_allowed(equipment.group, activity)
            and kocp_role_allowed(equipment.type, role, equipment.make_model)):
        raise HTTPException(422, f"Equipment is not assigned to {activity} {role.lower()} in KOCP Masters.")
    if role == "LOADING" and kocp_equipment_category(equipment.type, equipment.make_model) != "EXCAVATOR":
        raise HTTPException(422, "Select an excavator from KOCP Equipment Master.")
    return equipment


@router.get("/drivers")
def list_drivers(request: Request, operating_date: date, db: Session = Depends(get_db)):
    _auth(db, request, "TRIP", "VIEW")
    people = db.scalars(
        select(Person).join(PersonSiteAssignment).where(
            Person.active.is_(True),
            PersonSiteAssignment.site_id == "KOCP",
            PersonSiteAssignment.active.is_(True),
            PersonSiteAssignment.effective_from <= operating_date,
            or_(PersonSiteAssignment.effective_to.is_(None), PersonSiteAssignment.effective_to >= operating_date),
        ).distinct().order_by(Person.name, Person.employee_id)
    ).all()
    return [{"id": p.employee_id, "label": f"{p.name} — {p.employee_id}"} for p in people if _driver_role(p.role)]


def _card_lines(db, card_id):
    return list(db.scalars(select(SiteShiftTripCardLine).where(
        SiteShiftTripCardLine.card_id == card_id
    ).order_by(SiteShiftTripCardLine.line_no)))


def _detail(db, card):
    lines = _card_lines(db, card.card_id)
    return {
        "cardId": card.card_id, "kind": card.kind,
        "operatingDate": card.operating_date.isoformat(), "shift": card.shift,
        "sourceRef": card.source_ref, "relayCode": card.relay_source or "",
        "routeId": card.route_id or "", "materialId": card.material_id or "",
        "vehicleId": card.vehicle_id or "", "driverId": card.driver_id or "",
        "openingHmr": str(card.opening_hmr) if card.opening_hmr is not None else "",
        "closingHmr": str(card.closing_hmr) if card.closing_hmr is not None else "",
        "openingKmr": str(card.opening_kmr) if card.opening_kmr is not None else "",
        "closingKmr": str(card.closing_kmr) if card.closing_kmr is not None else "",
        "declaredTotal": card.declared_total, "status": card.status,
        "version": card.version, "enteredBy": card.entered_by,
        "enteredAt": card.entered_at.isoformat() if card.entered_at else None,
        "submittedBy": card.submitted_by,
        "submittedAt": card.submitted_at.isoformat() if card.submitted_at else None,
        "verifiedBy": card.verified_by,
        "reviewNote": card.review_note,
        "tripCount": sum(line.trip_count for line in lines),
        "rowCount": len(lines),
        "lines": [
            {"lineNo": line.line_no, "vehicleId": line.vehicle_id or "",
             "driverId": line.driver_id or "", "excavatorId": line.excavator_id or "",
             "patchCode": line.patch_source or "", "pointCode": line.unload_source or "",
              "sourceLocationId": line.source_location_id or "",
              "destinationLocationId": line.destination_location_id or "",
             "tripCount": line.trip_count, "routeId": line.route_id or "",
             "tripId": line.trip_id}
            for line in lines
        ],
    }


def _write_fields(db, card, payload, *, initial=False):
    kind = _source_code(payload.get("kind") or card.kind)
    if kind not in KINDS or (not initial and kind != card.kind):
        raise HTTPException(422, "Register kind cannot change.")
    operating_day = _date(payload.get("operatingDate"))
    shift = _source_code(payload.get("shift"))
    _site_shift_or_422(db, "KOCP", shift)
    lines = validate_register_lines(kind, payload.get("lines"))
    # Validate supplied selections before leaving a draft.
    material_id = _txt(payload.get("materialId"), 80)
    if material_id: _material(db, material_id, kind)
    default_route = _txt(payload.get("routeId"), 80)
    header_route = _route(db, default_route, kind, required=False)
    relay = _code(db, "RELAY", payload.get("relayCode"), required=False) if kind == "COAL" else None
    for line in lines:
        route = _route(db, line["routeId"], kind) if line.get("routeId") else header_route
        if kind == "COAL":
            _asset(db, line["vehicleId"], operating_day, "COAL", "TRANSPORT")
            if line["driverId"]:
                _driver(db, line["driverId"], operating_day)
        else:
            _asset(db, line["excavatorId"], operating_day, "OB", "LOADING")
            patch, unload, source, destination = _ob_locations(
                db, route, line["lineNo"], line["patchCode"], line["pointCode"],
                line["sourceLocationId"], line["destinationLocationId"],
            )
            line.update(patchCodeId=patch.code_id if patch else None,
                        unloadCodeId=unload.code_id if unload else None,
                        sourceLocationId=source, destinationLocationId=destination)
    if kind == "OB":
        if payload.get("vehicleId"):
            _asset(db, _txt(payload.get("vehicleId"),50), operating_day, "OB", "TRANSPORT")
        if payload.get("driverId"):
            _driver(db, _txt(payload.get("driverId"),50), operating_day)
    declared = payload.get("declaredTotal")
    if declared not in (None, ""):
        try:
            declared = int(declared)
        except (TypeError, ValueError):
            raise HTTPException(422, "Register declared total must be a whole number.")
        if declared < 0:
            raise HTTPException(422, "Register declared total cannot be negative.")
    else:
        declared = None
    hmropen, hmrclose = validate_meter_pair(payload.get("openingHmr"), payload.get("closingHmr"))
    kmropen, kmrclose = validate_meter_pair(payload.get("openingKmr"), payload.get("closingKmr"))
    card.kind, card.operating_date, card.shift = kind, operating_day, shift
    card.source_ref = _txt(payload.get("sourceRef"), 100) or None
    card.relay_source = relay.code if relay else None
    card.relay_code_id = relay.code_id if relay else None
    card.route_id = _txt(payload.get("routeId"), 80) or None
    card.material_id = _txt(payload.get("materialId"), 80) or None
    card.vehicle_id = _txt(payload.get("vehicleId"), 50) or None if kind == "OB" else None
    card.driver_id = _txt(payload.get("driverId"), 50) or None if kind == "OB" else None
    card.opening_hmr = Decimal(hmropen) if hmropen is not None and kind == "OB" else None
    card.closing_hmr = Decimal(hmrclose) if hmrclose is not None and kind == "OB" else None
    card.opening_kmr = Decimal(kmropen) if kmropen is not None and kind == "OB" else None
    card.closing_kmr = Decimal(kmrclose) if kmrclose is not None and kind == "OB" else None
    card.declared_total = declared
    for row in _card_lines(db, card.card_id):
        db.delete(row)
    db.flush()
    for line in lines:
        db.add(SiteShiftTripCardLine(
            line_id=f"SRL-{uuid4().hex[:20].upper()}", card_id=card.card_id,
            line_no=line["lineNo"], vehicle_id=line.get("vehicleId") or None,
            driver_id=line.get("driverId") or None,
            excavator_id=line.get("excavatorId") or None,
            patch_source=line.get("patchCode") or None,
            unload_source=line.get("pointCode") or None,
            patch_code_id=line.get("patchCodeId"), unload_code_id=line.get("unloadCodeId"),
            source_location_id=line.get("sourceLocationId"), destination_location_id=line.get("destinationLocationId"),
            route_id=line.get("routeId") or None, trip_count=line["tripCount"],
        ))
    db.flush()
    return lines


@router.get("/codes")
def list_operational_codes(request: Request, kind: str = "", db: Session = Depends(get_db)):
    user = get_user(db, request)
    require_site(db, user, "KOCP")
    if not user.admin and not any(has_permission(db, user, "KOCP", module, action)
            for module in ("TRIP", "MASTERS") for action in ("VIEW", "CREATE", "EDIT", "APPROVE")):
        raise HTTPException(403, "KOCP register or Masters permission required.")
    selected = _source_code(kind)
    if selected and selected not in CODE_KINDS:
        raise HTTPException(422, "Unknown master type.")
    stmt = select(SiteOperationalCode, SiteLocation).outerjoin(
        SiteLocation, SiteLocation.site_location_id == SiteOperationalCode.parent_location_id
    ).where(SiteOperationalCode.site_id == "KOCP")
    if selected:
        stmt = stmt.where(SiteOperationalCode.code_kind == selected)
    rows = db.execute(stmt.order_by(SiteOperationalCode.code_kind, SiteOperationalCode.code)).all()
    return [{
        "kind": code.code_kind, "code": code.code, "name": code.name, "active": code.active,
        "locationId": loc.site_location_id if loc and loc.active and loc.site_id == "KOCP" else "",
        "locationName": loc.name if loc and loc.active and loc.site_id == "KOCP" else "",
    } for code, loc in rows]


def _validate_code_location(db, kind, location_id):
    if kind in {"PATCH", "UNLOAD_POINT"} and not location_id:
        raise HTTPException(422, "Link the code to a KOCP physical location.")
    if location_id:
        _site_location_or_422(db, "KOCP", location_id)


@router.post("/codes")
def add_operational_code(payload: dict, request: Request, db: Session = Depends(get_db)):
    user = _auth(db, request, "MASTERS", "CREATE", True)
    kind = _source_code(payload.get("kind"))
    code = _source_code(payload.get("code"))
    name = _txt(payload.get("name"), 160)
    location_id = _txt(payload.get("locationId"), 80) or None
    if kind not in CODE_KINDS or not code or not name:
        raise HTTPException(422, "Choose a master type, code and name.")
    _validate_code_location(db, kind, location_id)
    ident = f"KOCP:{kind}:{code}"
    if db.get(SiteOperationalCode, ident):
        raise HTTPException(409, "Master code already exists; edit/deactivate the existing master.")
    row = SiteOperationalCode(code_id=ident,site_id="KOCP",code_kind=kind,code=code,
                              name=name,parent_location_id=location_id,active=True)
    db.add(row)
    _audit(db,user,"KOCP","CREATE_OPERATIONAL_CODE","site_operational_code",ident,
           after={"kind":kind,"code":code,"name":name,"locationId":location_id})
    db.commit()
    return {"ok":True,"code":code,"kind":kind}


@router.put("/codes")
def edit_operational_code(payload: dict, request: Request, db: Session = Depends(get_db)):
    user = _auth(db, request, "MASTERS", "EDIT", True)
    kind, code = _source_code(payload.get("kind")), _source_code(payload.get("code"))
    row = db.get(SiteOperationalCode, f"KOCP:{kind}:{code}")
    if not row:
        raise HTTPException(404, "KOCP Master code not found.")
    name = _txt(payload.get("name"), 160)
    location_id = _txt(payload.get("locationId"), 80) or None
    active = payload.get("active")
    if not name or not isinstance(active, bool):
        raise HTTPException(422, "Enter a name and valid status.")
    if active or location_id:
        _validate_code_location(db, row.code_kind, location_id)
    before = {"name": row.name, "locationId": row.parent_location_id, "active": row.active}
    row.name, row.parent_location_id, row.active = name, location_id, active
    _audit(db, user, "KOCP", "EDIT_OPERATIONAL_CODE", "site_operational_code", row.code_id,
           before=before, after={"name": name, "locationId": location_id, "active": active})
    db.commit()
    return {"ok": True}


@router.get("/cards")
def list_cards(request: Request, operating_date: date|None=None, kind: str="", db: Session=Depends(get_db)):
    _auth(db,request)
    stmt = select(SiteShiftTripCard).where(SiteShiftTripCard.site_id=="KOCP")
    if operating_date:
        stmt=stmt.where(SiteShiftTripCard.operating_date==operating_date)
    if kind:
        if _source_code(kind) not in KINDS: raise HTTPException(422,"Invalid register kind.")
        stmt=stmt.where(SiteShiftTripCard.kind==_source_code(kind))
    rows=list(db.scalars(stmt.order_by(
        SiteShiftTripCard.operating_date.desc(),SiteShiftTripCard.entered_at.desc()
    ).limit(250)))
    return [{key:value for key,value in _detail(db,row).items() if key!="lines"} for row in rows]



@router.get("/reports/management.xlsx")
def management_style_report(request: Request, from_date: date, to_date: date,
                            kind: str = "ALL", db: Session = Depends(get_db)):
    """September-style KOCP reports; no mutation and no historical imports."""
    user = get_user(db, request)
    require_site(db, user, "KOCP")
    from app.routers.site_ops import _require_any
    _require_any(db, user, "KOCP", "REPORTS")
    return build_kocp_management_report(db, from_date, to_date, kind)


@router.get("/review-queue")
def review_queue(request: Request, db: Session = Depends(get_db)):
    """Pending Coal/OB cards from all dates; ERP labels are read-only."""
    user = _auth(db, request)
    filters = (SiteShiftTripCard.site_id == "KOCP", SiteShiftTripCard.status == "SUBMITTED")
    total = db.scalar(select(func.count()).select_from(SiteShiftTripCard).where(*filters)) or 0
    cards = list(db.scalars(select(SiteShiftTripCard).where(*filters).order_by(
        SiteShiftTripCard.operating_date.asc(), SiteShiftTripCard.entered_at.asc(),
        SiteShiftTripCard.card_id,
    ).limit(301)))
    authorized = bool(user.admin or has_permission(db, user, "KOCP", "TRIP", "APPROVE"))
    items = []
    for card in cards[:300]:
        detail = _detail(db, card)
        detail["canVerify"] = bool(authorized and (user.admin or card.entered_by != user.login_id))
        items.append(detail)
    machine_ids, person_ids, material_ids, route_ids, loc_ids = set(), set(), set(), set(), set()
    for card in items:
        machine_ids.update(x for x in [card["vehicleId"]] if x)
        person_ids.update(x for x in [card["driverId"]] if x)
        material_ids.update(x for x in [card["materialId"]] if x)
        route_ids.update(x for x in [card["routeId"]] if x)
        for line in card["lines"]:
            machine_ids.update(x for x in [line["vehicleId"], line["excavatorId"]] if x)
            person_ids.update(x for x in [line["driverId"]] if x)
            route_ids.update(x for x in [line["routeId"]] if x)
            loc_ids.update(x for x in [line["sourceLocationId"], line["destinationLocationId"]] if x)
    machines = {x.machine_id: x for x in db.scalars(
        select(Equipment).where(Equipment.machine_id.in_(machine_ids))
    )} if machine_ids else {}
    persons = {x.employee_id: x.name for x in db.scalars(
        select(Person).where(Person.employee_id.in_(person_ids))
    )} if person_ids else {}
    materials = {x.site_material_id: x.name for x in db.scalars(
        select(SiteMaterial).where(SiteMaterial.site_id == "KOCP",
            SiteMaterial.site_material_id.in_(material_ids))
    )} if material_ids else {}
    routes = {x.route_id: x for x in db.scalars(
        select(SiteMovementRoute).where(SiteMovementRoute.site_id == "KOCP",
            SiteMovementRoute.route_id.in_(route_ids))
    )} if route_ids else {}
    locations = {x.site_location_id: x.name for x in db.scalars(
        select(SiteLocation).where(SiteLocation.site_id == "KOCP",
            SiteLocation.site_location_id.in_(loc_ids))
    )} if loc_ids else {}

    def machine_label(ident):
        eq = machines.get(ident)
        return " · ".join(str(x) for x in (
            f"Door {eq.door_no}" if eq and eq.door_no else None,
            eq.vehicle_no if eq else None, eq.make_model if eq else None
        ) if x) or ident

    def route_label(ident):
        route = routes.get(ident)
        return f"{route.route_group} → {route.destination_label} · {route.distance_range}" if route else ident

    for card in items:
        card["vehicleLabel"] = machine_label(card["vehicleId"])
        card["driverName"] = persons.get(card["driverId"], card["driverId"])
        card["materialName"] = materials.get(card["materialId"], card["materialId"])
        card["routeName"] = route_label(card["routeId"])
        for line in card["lines"]:
            line["vehicleLabel"] = machine_label(line["vehicleId"])
            line["excavatorLabel"] = machine_label(line["excavatorId"])
            line["driverName"] = persons.get(line["driverId"], line["driverId"])
            source = locations.get(line["sourceLocationId"], line["sourceLocationId"])
            dest = locations.get(line["destinationLocationId"], line["destinationLocationId"])
            line["sourceLocationName"] = source
            line["destinationLocationName"] = dest
            line["patchLabel"] = " — ".join(x for x in [line["patchCode"], source] if x)
            line["pointLabel"] = " — ".join(x for x in [line["pointCode"], dest] if x)
            line["routeName"] = route_label(line["routeId"] or card["routeId"])
    return {"totalPending": total, "hasMore": len(cards) > 300, "items": items}


@router.get("/cards/{card_id}")
def get_card(card_id: str,request:Request,db:Session=Depends(get_db)):
    _auth(db,request)
    row=db.get(SiteShiftTripCard,card_id)
    if not row or row.site_id!="KOCP": raise HTTPException(404,"Shift register not found.")
    return _detail(db,row)


@router.post("/cards")
def create_card(payload:dict,request:Request,db:Session=Depends(get_db)):
    user=_auth(db,request,"TRIP","CREATE",True)
    key=_txt(payload.get("clientKey"),120)
    if len(key)<12:
        raise HTTPException(422,"Client request key is required to prevent duplicate submissions.")
    existing=db.scalar(select(SiteShiftTripCard).where(
        SiteShiftTripCard.site_id=="KOCP",SiteShiftTripCard.client_key==key))
    if existing:
        return {"ok":True,"idempotent":True,**_detail(db,existing)}
    ident=f"SRC-KOCP-{uuid4().hex[:17].upper()}"
    row=SiteShiftTripCard(card_id=ident,site_id="KOCP",kind=_source_code(payload.get("kind")),
                          operating_date=_date(payload.get("operatingDate")),shift=_source_code(payload.get("shift")),
                          client_key=key,entered_by=user.login_id,status="DRAFT",version=1)
    db.add(row)
    db.flush()
    _write_fields(db,row,payload,initial=True)
    _audit(db,user,"KOCP","CREATE_SHIFT_REGISTER","site_shift_trip_card",ident,
           after={"kind":row.kind,"date":str(row.operating_date),"shift":row.shift})
    db.commit()
    return {"ok":True,**_detail(db,row)}


@router.put("/cards/{card_id}")
def edit_card(card_id:str,payload:dict,request:Request,db:Session=Depends(get_db)):
    user=_auth(db,request,"TRIP","CREATE",True)
    row=db.scalar(select(SiteShiftTripCard).where(
        SiteShiftTripCard.card_id==card_id,SiteShiftTripCard.site_id=="KOCP"
    ).with_for_update())
    if not row:raise HTTPException(404,"Shift register not found.")
    if not user.admin and row.entered_by!=user.login_id and not has_permission(db,user,"KOCP","TRIP","EDIT"):
        raise HTTPException(403,"Only the creator or authorized editor can change this register.")
    if row.status not in {"DRAFT","REJECTED"}:
        raise HTTPException(409,"Only draft/rejected registers can be edited.")
    if payload.get("expectedVersion")!=row.version:
        raise HTTPException(409,"Register changed. Reload and try again.")
    before={"version":row.version,"status":row.status,"tripCount":sum(x.trip_count for x in _card_lines(db,card_id))}
    _write_fields(db,row,payload)
    row.version+=1
    row.status="DRAFT"
    _audit(db,user,"KOCP","EDIT_SHIFT_REGISTER","site_shift_trip_card",card_id,
           before=before,after={"version":row.version,"tripCount":sum(x.trip_count for x in _card_lines(db,card_id))})
    db.commit()
    return {"ok":True,**_detail(db,row)}


def _source_signature(card, lines):
    """A second browser/PC cannot repost the identical paper under a new key."""
    if card.kind == "COAL":
        entries = [(l.vehicle_id,l.driver_id,l.trip_count,l.route_id or card.route_id)
                   for l in lines]
    else:
        counts = Counter()
        for line in lines:
            group = (line.excavator_id, line.source_location_id or line.patch_source,
                     line.destination_location_id or line.unload_source, line.route_id or card.route_id)
            counts[group] += line.trip_count
        entries = [(*group, count) for group, count in counts.items()]
    return (
        card.kind, card.operating_date, card.shift,
        card.vehicle_id if card.kind == "OB" else card.relay_source,
        card.route_id, card.material_id,
        tuple(sorted(entries, key=lambda x: str(x))),
    )


@router.post("/cards/{card_id}/submit")
def submit_card(card_id:str,payload:dict,request:Request,db:Session=Depends(get_db)):
    user=_auth(db,request,"TRIP","CREATE",True)
    row=db.scalar(select(SiteShiftTripCard).where(
        SiteShiftTripCard.card_id==card_id,SiteShiftTripCard.site_id=="KOCP"
    ).with_for_update())
    if not row:raise HTTPException(404,"Shift register not found.")
    if row.status=="SUBMITTED": return {"ok":True,"idempotent":True,**_detail(db,row)}
    if row.status not in {"DRAFT","REJECTED"}:
        raise HTTPException(409,"This register is already verified or cannot be submitted.")
    if payload.get("expectedVersion")!=row.version:
        raise HTTPException(409,"Register changed. Reload before submitting.")
    lines=_card_lines(db,card_id)
    total=sum(x.trip_count for x in lines)
    if not total or (row.declared_total is not None and row.declared_total!=total):
        raise HTTPException(422,"Reported paper total does not match entered trip counts.")
    _material(db, row.material_id, row.kind)
    if row.kind == "OB":
        _asset(db, row.vehicle_id, row.operating_date, "OB", "TRANSPORT")
        if row.driver_id:
            _driver(db, row.driver_id, row.operating_date)
    if row.relay_source:
        _code(db, "RELAY", row.relay_source)
    for line in lines:
        route = _route(db, line.route_id or row.route_id, row.kind)
        if row.kind == "OB":
            _ob_locations(db, route, line.line_no, line.patch_source, line.unload_source,
                          line.source_location_id, line.destination_location_id)
            _asset(db, line.excavator_id, row.operating_date, "OB", "LOADING")
        else:
            if line.driver_id:
                _driver(db, line.driver_id, row.operating_date)
            _asset(db, line.vehicle_id, row.operating_date, "COAL", "TRANSPORT")
    # On repeat submissions from a different browser, detect the same source
    # reference or identical paper content before allowing MIS review.
    others=db.scalars(select(SiteShiftTripCard).where(
        SiteShiftTripCard.site_id=="KOCP",SiteShiftTripCard.kind==row.kind,
        SiteShiftTripCard.operating_date==row.operating_date,
        SiteShiftTripCard.shift==row.shift,
        SiteShiftTripCard.card_id!=row.card_id,
        SiteShiftTripCard.status.in_(["SUBMITTED","VERIFIED"]),
    )).all()
    signature=_source_signature(row,lines)
    for other in others:
        if (row.source_ref and other.source_ref and
                row.source_ref.casefold()==other.source_ref.casefold()):
            raise HTTPException(409,"A register with this paper reference is already submitted.")
        if _source_signature(other,_card_lines(db,other.card_id))==signature:
            raise HTTPException(409,"This same Coal/OB paper content has already been submitted.")
    row.status="SUBMITTED";row.submitted_by=user.login_id
    row.submitted_at=datetime.now(timezone.utc);row.version+=1
    _audit(db,user,"KOCP","SUBMIT_SHIFT_REGISTER","site_shift_trip_card",card_id,
           after={"total":total,"status":"SUBMITTED"})
    db.commit()
    return {"ok":True,**_detail(db,row)}


def _save_meter(db,user,card,meter_type,opening,closing):
    if opening is None and closing is None:
        return
    existing=db.scalar(select(SiteAssetMeter).where(
        SiteAssetMeter.site_id=="KOCP",SiteAssetMeter.operating_date==card.operating_date,
        SiteAssetMeter.shift==card.shift,SiteAssetMeter.asset_id==card.vehicle_id,
        SiteAssetMeter.meter_type==meter_type,
    ).with_for_update())
    if existing:
        if existing.opening_reading!=opening or existing.closing_reading!=closing:
            raise HTTPException(409,f"Conflicting {meter_type} reading already saved for this vehicle/shift.")
        return
    db.add(SiteAssetMeter(
        reading_id=f"MTR-KOCP-{uuid4().hex[:14].upper()}",site_id="KOCP",
        operating_date=card.operating_date,shift=card.shift,asset_id=card.vehicle_id,
        meter_type=meter_type,opening_reading=opening,closing_reading=closing,
        usage=closing-opening,source_type="SHIFT_OB_CARD",remarks=card.card_id,
        entered_by=user.login_id,
    ))


@router.post("/cards/{card_id}/decision")
def decide_card(card_id:str,payload:dict,request:Request,db:Session=Depends(get_db)):
    user=_auth(db,request,"TRIP","APPROVE",True)
    action=_source_code(payload.get("action"))
    if action not in {"VERIFY","REJECT"}:
        raise HTTPException(422,"Choose Verify or Reject.")
    row=db.scalar(select(SiteShiftTripCard).where(
        SiteShiftTripCard.card_id==card_id,SiteShiftTripCard.site_id=="KOCP"
    ).with_for_update())
    if not row:raise HTTPException(404,"Shift register not found.")
    if row.status=="VERIFIED" and action=="VERIFY":
        return {"ok":True,"idempotent":True,**_detail(db,row)}
    if row.status!="SUBMITTED":
        raise HTTPException(409,"Only submitted registers can be reviewed.")
    if payload.get("expectedVersion")!=row.version:
        raise HTTPException(409,"Register version changed. Reload before verification.")
    if action=="REJECT":
        reason=_txt(payload.get("reason"),500)
        if len(reason)<5:
            raise HTTPException(422,"State the correction reason (at least 5 characters).")
        row.status="REJECTED";row.review_note=reason;row.version+=1
        _audit(db,user,"KOCP","REJECT_SHIFT_REGISTER","site_shift_trip_card",card_id,reason=reason)
        db.commit()
        return {"ok":True,**_detail(db,row)}
    if row.entered_by==user.login_id and not user.admin:
        raise HTTPException(403,"A different MIS checker must verify this source register.")
    if row.declared_total is not None and row.declared_total!=sum(x.trip_count for x in _card_lines(db,card_id)):
        raise HTTPException(422,"Paper total is not equal to entered trips.")
    _site_shift_or_422(db,"KOCP",row.shift)
    material=_material(db,row.material_id,row.kind)
    if row.relay_source:
        relay=_code(db,"RELAY",row.relay_source)
        row.relay_code_id=relay.code_id
    if row.kind=="OB":
        vehicle=_asset(db, row.vehicle_id, row.operating_date, "OB", "TRANSPORT")
        if row.driver_id:
            _driver(db, row.driver_id, row.operating_date)
        if row.opening_hmr is not None and row.closing_hmr is not None:
            _save_meter(db,user,row,"HMR",row.opening_hmr,row.closing_hmr)
        if row.opening_kmr is not None and row.closing_kmr is not None:
            _save_meter(db,user,row,"KMR",row.opening_kmr,row.closing_kmr)
    else:
        vehicle=None
    billing=db.scalar(select(SiteBillingReconciliation.billing_id).where(
        SiteBillingReconciliation.site_id=="KOCP",SiteBillingReconciliation.status=="APPROVED",
        SiteBillingReconciliation.period_start<=row.operating_date,
        SiteBillingReconciliation.period_end>=row.operating_date,
        SiteBillingReconciliation.material_id==material.site_material_id,
    ).limit(1))
    if billing:
        raise HTTPException(409,"Approved MCL billing period is locked. Request a billing revision first.")
    if row.kind=="OB":
        duplicate=db.scalar(select(SiteShiftTripCard.card_id).where(
            SiteShiftTripCard.site_id=="KOCP",SiteShiftTripCard.kind=="OB",
            SiteShiftTripCard.operating_date==row.operating_date,
            SiteShiftTripCard.shift==row.shift,
            SiteShiftTripCard.vehicle_id==row.vehicle_id,
            SiteShiftTripCard.status=="VERIFIED",
            SiteShiftTripCard.card_id!=row.card_id,
        ).limit(1))
        if duplicate:
            raise HTTPException(409,"This OB tipper already has a verified card for this shift.")
    lines=_card_lines(db,card_id)
    result={"tripCount":0,"pendingFactorTrips":0}
    for line in lines:
        if line.trip_id:
            raise HTTPException(409,"This source row was already posted.")
        count=line.trip_count
        vehicle_id=line.vehicle_id if row.kind=="COAL" else row.vehicle_id
        driver_id=line.driver_id if row.kind=="COAL" else row.driver_id
        eq=_asset(db, vehicle_id, row.operating_date, row.kind, "TRANSPORT")
        if driver_id:
            _driver(db, driver_id, row.operating_date)
        excavator_id=line.excavator_id if row.kind=="OB" else None
        if excavator_id:
            _asset(db, excavator_id, row.operating_date, "OB", "LOADING")
        route=_route(db,line.route_id or row.route_id,row.kind)
        dest_id=route.destination_location_id
        if row.kind=="OB":
            patch, unload, source, destination = _ob_locations(
                db, route, line.line_no, line.patch_source, line.unload_source,
                line.source_location_id, line.destination_location_id,
            )
            line.patch_code_id = patch.code_id if patch else None
            line.unload_code_id = unload.code_id if unload else None
            line.source_location_id = source
            line.destination_location_id = destination
        factor=None
        try:
            factor=resolve_kocp_point_factor(
                db,factor_type="OB_CUM_PER_TRIP" if row.kind=="OB" else "COAL_AVG_MT_PER_TRIP",
                operating_day=row.operating_date,shift=row.shift,destination_id=dest_id,
                route_id=route.route_id,material_id=material.site_material_id,
                vehicle_type=eq.type,vehicle_group=eq.group,vehicle_model=eq.make_model,
            )
        except HTTPException as error:
            if error.status_code!=409:raise
        qty=Decimal(str(factor.factor_value))*count if factor else None
        ident=f"TRIP-KOCP-{uuid4().hex[:14].upper()}"
        db.add(SiteTrip(
            trip_id=ident,site_id="KOCP",operating_date=row.operating_date,
            shift=row.shift,event_at=None,vehicle_id=vehicle_id,driver_id=driver_id,
            loading_equipment_id=excavator_id,route_id=route.route_id,
            source_location_id=route.source_location_id,
            destination_location_id=dest_id,material_id=material.site_material_id,
            trip_seq=line.line_no if row.kind=="OB" else None,
            trip_count=count,quantity_cum=qty if row.kind=="OB" else None,
            quantity_mt=qty if row.kind=="COAL" else None,
            weight_basis=("MCL_DUMPER_FACTOR" if row.kind=="OB" else "MCL_SHIFT_AVERAGE") if factor else "PENDING_FACTOR",
            factor_id=factor.factor_id if factor else None,
            source_type="SHIFT_OB_CARD" if row.kind=="OB" else "SHIFT_COAL_REGISTER",
            source_record_uid=f"{card_id}:{line.line_no}",status="POSTED",
            entered_by=user.login_id,
        ))
        # Insert the parent trip before assigning its FK to the paper line.
        # Otherwise SQLAlchemy may UPDATE the child first (PostgreSQL 23503).
        db.flush()
        line.trip_id=ident
        result["tripCount"]+=count
        if not factor:
            result["pendingFactorTrips"]+=count
    row.status="VERIFIED";row.version+=1;row.verified_by=user.login_id
    row.verified_at=datetime.now(timezone.utc);row.review_note=_txt(payload.get("reason"),500) or None
    _audit(db,user,"KOCP","VERIFY_SHIFT_REGISTER","site_shift_trip_card",card_id,
           after={**result,"kind":row.kind,"status":"VERIFIED"})
    db.commit()
    return {"ok":True,**result,**_detail(db,row)}


def refresh_verified_pending_factors(db: Session, user, factor: SiteWeightFactor):
    """Recompute quantity when a dated *daily* factor is approved.

    Only source-derived quantities are updated. Never mutate paper rows or
    certified monthly billing, and never rewrite an approved billing period.
    """
    if (factor.site_id != "KOCP" or factor.status != "APPROVED" or
            (factor.source_org or "").upper() not in {"DAILY_REPORT","MCL"}):
        return 0
    stmt=select(SiteTrip).where(
        SiteTrip.site_id=="KOCP",
        SiteTrip.source_type.in_(["SHIFT_COAL_REGISTER","SHIFT_OB_CARD"]),
        SiteTrip.status=="POSTED",SiteTrip.factor_id.is_(None),
        SiteTrip.operating_date>=factor.effective_from,
        SiteTrip.destination_location_id==factor.destination_location_id,
    )
    if factor.effective_to:
        stmt=stmt.where(SiteTrip.operating_date<=factor.effective_to)
    if factor.operating_date:
        stmt=stmt.where(SiteTrip.operating_date==factor.operating_date)
    if factor.material_id:
        stmt=stmt.where(SiteTrip.material_id==factor.material_id)
    if factor.route_id:
        stmt=stmt.where(SiteTrip.route_id==factor.route_id)
    if factor.shift:
        stmt=stmt.where(SiteTrip.shift==factor.shift)
    updated=0
    for trip in db.scalars(stmt).all():
        billed=db.scalar(select(SiteBillingReconciliation.billing_id).where(
            SiteBillingReconciliation.site_id=="KOCP",
            SiteBillingReconciliation.status=="APPROVED",
            SiteBillingReconciliation.period_start<=trip.operating_date,
            SiteBillingReconciliation.period_end>=trip.operating_date,
            SiteBillingReconciliation.material_id==trip.material_id,
        ).limit(1))
        if billed:
            continue
        machine=db.get(Equipment,trip.vehicle_id)
        if not machine:
            continue
        kind="OB" if trip.source_type=="SHIFT_OB_CARD" else "COAL"
        try:
            selected=resolve_kocp_point_factor(
                db,factor_type="OB_CUM_PER_TRIP" if kind=="OB" else "COAL_AVG_MT_PER_TRIP",
                operating_day=trip.operating_date,shift=trip.shift,
                destination_id=trip.destination_location_id,
                route_id=trip.route_id,material_id=trip.material_id,
                vehicle_type=machine.type,vehicle_group=machine.group,vehicle_model=machine.make_model,
            )
        except HTTPException as error:
            if error.status_code==409:
                continue
            raise
        qty=Decimal(str(selected.factor_value))*trip.trip_count
        if kind=="OB":
            trip.quantity_cum=qty
            trip.weight_basis="MCL_DUMPER_FACTOR"
        else:
            trip.quantity_mt=qty
            trip.weight_basis="MCL_SHIFT_AVERAGE"
        trip.factor_id=selected.factor_id
        trip.version=(trip.version or 1)+1
        trip.updated_at=datetime.now(timezone.utc)
        _audit(db,user,"KOCP","APPLY_APPROVED_DAILY_FACTOR","site_trip",trip.trip_id,
               after={"factorId":selected.factor_id,"tripCount":trip.trip_count,"quantity":str(qty),"kind":kind})
        updated+=1
    return updated


@router.get("/summary")
def shift_register_summary(request:Request,operating_date:date,db:Session=Depends(get_db)):
    _auth(db,request)
    cards=db.scalars(select(SiteShiftTripCard).where(
        SiteShiftTripCard.site_id=="KOCP",
        SiteShiftTripCard.operating_date==operating_date
    )).all()
    result={"COAL":{"cards":0,"verified":0,"trips":0,"pendingFactorTrips":0},
            "OB":{"cards":0,"verified":0,"trips":0,"pendingFactorTrips":0}}
    for card in cards:
        item=result[card.kind]
        item["cards"]+=1
        if card.status=="VERIFIED":
            item["verified"]+=1
            for line in _card_lines(db,card.card_id):
                item["trips"]+=line.trip_count
                trip=db.get(SiteTrip,line.trip_id) if line.trip_id else None
                if trip and trip.factor_id is None:
                    item["pendingFactorTrips"]+=line.trip_count
    return {"date":operating_date.isoformat(),"kinds":result}
