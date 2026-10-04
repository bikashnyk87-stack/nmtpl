from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from uuid import uuid4
import json

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth import WebSession, WebUser, csrf, get_user, hash_password
from app.db import get_db
from app.models import Equipment, LoadTrip, Person, WbMovement
from app.site_auth import accessible_sites, has_permission, require_permission, require_site
from app.site_models import (
    EquipmentSiteAssignment,
    MasterImportBatch,
    MasterImportRow,
    PersonSiteAssignment,
    Site,
    SiteAuditLog,
    SiteHsdTransaction,
    SiteLocation,
    SiteMaterial,
    SiteShift,
    SiteTrip,
    SiteWbMovement,
    SiteWeightFactor,
    UserPermission,
    UserSiteAccess,
)
from app.site_schemas import (
    SiteHsdTransactionIn,
    SiteTripIn,
    SiteWbManualIn,
    WeightFactorDecisionIn,
    WeightFactorIn,
    UserSitePermissionPlanIn,
    UserAccountCreateIn,
    UserAccountUpdateIn,
)
from app.services.site_context import resolve_site_context

router = APIRouter(prefix="/api/sites", tags=["multi-site"])


MODULES_BY_SITE = {
    # v0.10 exposes the complete agreed workspace catalogue from day one.
    # Fine-grained access still decides which of these modules a non-admin can see.
    "TIOM": [
        "DASHBOARD", "ATTENDANCE", "SHIFT_CONTROL", "PRODUCTION", "FIELD_ENTRY", "MIS",
        "WB", "RECONCILIATION", "HSD", "GPS", "FLEET", "LOADER", "EXCAVATOR",
        "MECHANICAL", "REPORTS", "MASTERS", "DATA_QUALITY", "MAP", "SATELLITE", "AUDIT",
    ],
    "SOCP": [
        "DASHBOARD", "ATTENDANCE", "SHIFT_CONTROL", "TRIP", "WB", "RECONCILIATION",
        "HSD", "FLEET", "LOADER", "DRIVER", "GP_DESTINATION", "REPORTS", "MASTERS",
        "DATA_QUALITY", "MAP", "SATELLITE", "AUDIT",
    ],
    "KOCP": [
        "DASHBOARD", "ATTENDANCE", "SHIFT_CONTROL", "TRIP", "OB", "MCL_FACTOR",
        "MCL_SURVEY", "RECONCILIATION", "HSD", "FLEET", "LOADER", "EXCAVATOR",
        "HMR_KMR", "BILLING", "REPORTS", "MASTERS", "DATA_QUALITY", "MAP",
        "SATELLITE", "AUDIT",
    ],
}

MASTER_TEMPLATES = {
    "EMPLOYEE": {
        "headers": ["Employee ID", "Employee Name", "Role", "Department", "Mobile", "Effective From", "Active"],
        "required": {"Employee ID", "Employee Name", "Role"},
        "sample": ["EMP001", "Sample Employee", "DRIVER", "OPERATIONS", "9999999999", "2026-09-30", "TRUE"],
    },
    "VEHICLE": {
        "headers": ["Machine ID", "Registration No", "Door No", "Type", "Group", "Ownership", "Party", "Effective From", "Active"],
        "required": {"Machine ID", "Type", "Group"},
        "sample": ["V001", "OD-XX-0001", "1", "TIPPER", "VEHICLE", "OWN", "NMTPL", "2026-09-30", "TRUE"],
    },
    "EQUIPMENT": {
        "headers": ["Machine ID", "Door No", "Vehicle No", "Type", "Group", "Make Model", "Bucket CuM", "Rated Payload T", "Ownership", "Effective From", "Active"],
        "required": {"Machine ID", "Type", "Group"},
        "sample": ["L001", "L-01", "", "LOADER", "LOADER", "SDLG", "3.5", "", "OWN", "2026-09-30", "TRUE"],
    },
    "LOCATION": {
        "headers": ["Code", "Location Name", "Role", "Location Type", "Distance KM", "Latitude", "Longitude", "Active"],
        "required": {"Code", "Location Name"},
        "sample": ["RLS", "RLS Siding", "DESTINATION", "UNLOADING", "7.5", "", "", "TRUE"],
    },
    "MATERIAL": {
        "headers": ["Code", "Material Name", "Material Group", "Default Unit", "Billable Unit", "Active"],
        "required": {"Code", "Material Name", "Default Unit"},
        "sample": ["OB", "Over Burden", "OB", "CUM", "CUM", "TRUE"],
    },
}


def _bool(value, default=True):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().upper() in {"TRUE", "YES", "Y", "1", "ACTIVE"}


def _date(value, default=None):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return default
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Invalid date: {raw}")


def _clean(value):
    return str(value).strip() if value not in (None, "") else None


def _audit(db: Session, user, site_id: str | None, action: str, entity: str, entity_id: str | None, before=None, after=None, reason=None):
    db.add(SiteAuditLog(
        site_id=site_id,
        actor=user.login_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        before_json=json.dumps(before, default=str) if before is not None else None,
        after_json=json.dumps(after, default=str) if after is not None else None,
        reason=reason,
    ))


def _site_modules(db: Session, user, site_id: str) -> list[str]:
    base = MODULES_BY_SITE.get(site_id, [])
    if user.admin:
        return base
    allowed = []
    for module in base:
        if any(has_permission(db, user, site_id, module, action) for action in ("VIEW", "CREATE", "EDIT", "APPROVE", "ALL")):
            allowed.append(module)
    return allowed


@router.get("/bootstrap")
def bootstrap(request: Request, db: Session = Depends(get_db)):
    user = get_user(db, request)
    allowed = accessible_sites(db, user)
    sites = []
    for row in db.scalars(select(Site).where(Site.active.is_(True)).order_by(Site.site_id)):
        if row.site_id not in allowed:
            continue
        sites.append({
            "siteId": row.site_id,
            "siteName": row.site_name,
            "shortName": row.short_name,
            "mapConfigured": bool(row.map_url),
            "modules": _site_modules(db, user, row.site_id),
        })
    central_view = user.admin or any(has_permission(db, user, s, "DASHBOARD", "VIEW") for s in allowed)
    return {
        "ok": True,
        "version": "1.0.0-tiom1.9-mechanical-final",
        "user": {"loginId": user.login_id, "name": user.name, "isManagement": user.admin},
        "canViewCentralDashboard": central_view,
        "sites": sites,
    }


def _normalise_access_plan(db: Session, sites_raw, permissions_raw, default_site_raw):
    sites = {str(x).upper().strip() for x in (sites_raw or []) if str(x).strip()}
    known_sites = set(db.scalars(select(Site.site_id).where(Site.active.is_(True))))
    if not sites <= known_sites:
        unknown = sorted(sites - known_sites)
        raise HTTPException(422, "Unknown site(s) in access plan: " + ", ".join(unknown))
    default_site = str(default_site_raw).upper().strip() if default_site_raw else None
    if default_site and default_site not in sites:
        raise HTTPException(422, "Default site must be one of the assigned sites.")
    parsed = []
    allowed_actions = {"VIEW", "CREATE", "EDIT", "APPROVE", "EXPORT", "ALL"}
    for raw in permissions_raw or []:
        parts = str(raw).upper().strip().split(".")
        if len(parts) != 3:
            raise HTTPException(422, f"Invalid permission: {raw}")
        site, module, action = parts
        if site not in sites or module not in MODULES_BY_SITE.get(site, []) or action not in allowed_actions:
            raise HTTPException(422, f"Permission is not valid for assigned site: {raw}")
        parsed.append((site, module, action, f"{site}.{module}.{action}"))
    return sites, known_sites, default_site, parsed


def _apply_access_plan(db: Session, actor, target: WebUser, sites_raw, permissions_raw, default_site_raw):
    sites, known_sites, default_site, parsed = _normalise_access_plan(db, sites_raw, permissions_raw, default_site_raw)
    existing_access = {r.site_id: r for r in db.scalars(select(UserSiteAccess).where(UserSiteAccess.login_id == target.login_id))}
    for site in known_sites:
        row = existing_access.get(site)
        if site in sites:
            if not row:
                row = UserSiteAccess(login_id=target.login_id, site_id=site, assigned_by=actor.login_id)
                db.add(row)
            row.active = True
            row.default_site = site == default_site
            row.assigned_by = actor.login_id
        elif row:
            row.active = False
            row.default_site = False
            row.assigned_by = actor.login_id

    for old in db.scalars(select(UserPermission).where(UserPermission.login_id == target.login_id)):
        db.delete(old)
    db.flush()
    for site, module, action, permission in sorted(set(parsed)):
        db.add(UserPermission(
            login_id=target.login_id,
            site_id=site,
            module=module,
            action=action,
            permission=permission,
            active=True,
            assigned_by=actor.login_id,
        ))
    return sorted(sites), default_site, sorted({x[3] for x in parsed})


@router.post("/admin/users")
def create_user_account(p: UserAccountCreateIn, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    actor = get_user(db, request)
    if not actor.admin:
        raise HTTPException(403, "Management access required.")
    login_id = p.loginId.lower().strip()
    if db.get(WebUser, login_id):
        raise HTTPException(409, "User ID already exists.")
    target = WebUser(
        login_id=login_id,
        name=p.name.strip(),
        password_hash=hash_password(p.password),
        modules="",
        shifts="",
        admin=p.admin,
        active=p.active,
    )
    db.add(target)
    db.flush()
    sites, default_site, permissions = _apply_access_plan(db, actor, target, p.sites, p.permissions, p.defaultSite)
    _audit(db, actor, None, "CREATE_USER_ACCOUNT", "web_user", target.login_id,
           after={"name": target.name, "admin": target.admin, "active": target.active,
                  "sites": sites, "defaultSite": default_site, "permissions": permissions})
    db.commit()
    return {"ok": True, "loginId": target.login_id, "sites": sites, "defaultSite": default_site, "permissions": permissions}


@router.post("/admin/users/{login_id}")
def update_user_account(login_id: str, p: UserAccountUpdateIn, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    actor = get_user(db, request)
    if not actor.admin:
        raise HTTPException(403, "Management access required.")
    target = db.get(WebUser, login_id.lower())
    if not target:
        raise HTTPException(404, "Account not found.")
    if target.login_id == actor.login_id:
        if p.active is False:
            raise HTTPException(409, "You cannot disable your own account.")
        if p.admin is False:
            raise HTTPException(409, "You cannot remove your own management access.")
    before = {"name": target.name, "admin": target.admin, "active": target.active}
    if p.name is not None:
        target.name = p.name.strip()
    if p.admin is not None:
        target.admin = p.admin
    if p.active is not None:
        target.active = p.active
    if p.password is not None:
        target.password_hash = hash_password(p.password)
        target.failed_attempts = 0
        target.locked_until = None
        db.execute(delete(WebSession).where(WebSession.login_id == target.login_id))
    _audit(db, actor, None, "UPDATE_USER_ACCOUNT", "web_user", target.login_id,
           before=before, after={"name": target.name, "admin": target.admin, "active": target.active,
                                 "passwordReset": p.password is not None})
    db.commit()
    return {"ok": True, "loginId": target.login_id, "name": target.name, "admin": target.admin, "active": target.active}


@router.get("/admin/access")
def get_access_matrix(request: Request, db: Session = Depends(get_db)):
    user = get_user(db, request)
    if not user.admin:
        raise HTTPException(403, "Management access required.")
    output = []
    for account in db.scalars(select(WebUser).order_by(WebUser.login_id)):
        site_rows = list(db.scalars(select(UserSiteAccess).where(UserSiteAccess.login_id == account.login_id, UserSiteAccess.active.is_(True))))
        permissions = list(db.scalars(select(UserPermission.permission).where(UserPermission.login_id == account.login_id, UserPermission.active.is_(True)).order_by(UserPermission.permission)))
        output.append({
            "loginId": account.login_id,
            "name": account.name,
            "admin": account.admin,
            "active": account.active,
            "sites": [r.site_id for r in site_rows],
            "defaultSite": next((r.site_id for r in site_rows if r.default_site), None),
            "permissions": permissions,
        })
    return output


@router.post("/admin/access/{login_id}")
def save_access_matrix(login_id: str, p: UserSitePermissionPlanIn, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    user = get_user(db, request)
    if not user.admin:
        raise HTTPException(403, "Management access required.")
    target = db.get(WebUser, login_id.lower())
    if not target:
        raise HTTPException(404, "Account not found.")
    sites, default_site, permissions = _apply_access_plan(db, user, target, p.sites, p.permissions, p.defaultSite)
    _audit(db, user, None, "SAVE_ACCESS_PLAN", "web_user", target.login_id, after={"sites": sites, "defaultSite": default_site, "permissions": permissions})
    db.commit()
    return {"ok": True, "loginId": target.login_id, "sites": sites, "defaultSite": default_site, "permissions": permissions}


@router.get("/{site_id}/context")
def site_context(site_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    ctx = resolve_site_context(db, site_id)
    shifts = [{
        "shift": s.shift,
        "start": s.start_time.strftime("%H:%M"),
        "end": s.end_time.strftime("%H:%M"),
    } for s in db.scalars(select(SiteShift).where(SiteShift.site_id == site_id, SiteShift.active.is_(True)).order_by(SiteShift.sequence_no))]
    site = db.get(Site, site_id)
    return {
        "siteId": site_id,
        "siteName": site.site_name,
        "operatingDate": ctx.operating_date,
        "shift": ctx.shift,
        "localTime": ctx.local_at,
        "shifts": shifts,
        "modules": _site_modules(db, user, site_id),
        "mapUrl": site.map_url,
    }


@router.get("/{site_id}/dashboard")
def dashboard(site_id: str, request: Request, operating_date: date | None = None, db: Session = Depends(get_db)):
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    if not user.admin and not has_permission(db, user, site_id, "DASHBOARD", "VIEW"):
        raise HTTPException(403, "Dashboard permission is required.")
    day = operating_date or resolve_site_context(db, site_id).operating_date

    if site_id == "TIOM":
        # Read legacy TIOM tables without changing their schema during v0.9.
        trips = db.scalar(select(func.count()).select_from(LoadTrip).where(LoadTrip.operating_date == day)) or 0
        wb_rows = db.scalar(select(func.count()).select_from(WbMovement).where(WbMovement.operating_date == day)) or 0
        net_kg = db.scalar(select(func.coalesce(func.sum(WbMovement.net_kg), 0)).where(WbMovement.operating_date == day)) or 0
        return {"siteId": site_id, "date": day, "source": "LEGACY_TIOM", "trips": trips, "wbRows": wb_rows, "quantityMt": float(Decimal(net_kg) / Decimal(1000))}

    trips = db.scalar(select(func.count()).select_from(SiteTrip).where(SiteTrip.site_id == site_id, SiteTrip.operating_date == day, SiteTrip.status != "VOID")) or 0
    qty_mt = db.scalar(select(func.coalesce(func.sum(SiteTrip.quantity_mt), 0)).where(SiteTrip.site_id == site_id, SiteTrip.operating_date == day, SiteTrip.status != "VOID")) or 0
    qty_cum = db.scalar(select(func.coalesce(func.sum(SiteTrip.quantity_cum), 0)).where(SiteTrip.site_id == site_id, SiteTrip.operating_date == day, SiteTrip.status != "VOID")) or 0
    wb_rows = db.scalar(select(func.count()).select_from(SiteWbMovement).where(SiteWbMovement.site_id == site_id, SiteWbMovement.operating_date == day, SiteWbMovement.row_status == "VALID")) or 0
    hsd_issue = db.scalar(select(func.coalesce(func.sum(SiteHsdTransaction.litres), 0)).where(SiteHsdTransaction.site_id == site_id, SiteHsdTransaction.operating_date == day, SiteHsdTransaction.transaction_type == "ISSUE", SiteHsdTransaction.status == "POSTED")) or 0
    return {
        "siteId": site_id,
        "date": day,
        "source": "MULTISITE",
        "trips": trips,
        "quantityMt": float(qty_mt),
        "quantityCum": float(qty_cum),
        "wbRows": wb_rows,
        "hsdIssuedL": float(hsd_issue),
    }


@router.get("/{site_id}/masters/{master_type}/template.xlsx")
def master_template(site_id: str, master_type: str, request: Request, db: Session = Depends(get_db)):
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    if not user.admin and not (has_permission(db, user, site_id, "MASTERS", "VIEW") or has_permission(db, user, site_id, "MASTERS", "CREATE")):
        raise HTTPException(403, "Master access is required.")
    key = master_type.upper()
    spec = MASTER_TEMPLATES.get(key)
    if not spec:
        raise HTTPException(404, "Unknown master template.")
    wb = Workbook()
    ws = wb.active
    ws.title = key.title()
    ws.append(spec["headers"])
    ws.append(spec["sample"])
    meta = wb.create_sheet("Instructions")
    meta.append(["NMTPL Master Upload Template"])
    meta.append(["Site", site_id])
    meta.append(["Master", key])
    meta.append(["Required Columns", ", ".join(sorted(spec["required"]))])
    meta.append(["Rule", "Do not rename header cells. Delete the sample row before production upload."])
    data = BytesIO(); wb.save(data); data.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="NMTPL_{site_id}_{key}_Template.xlsx"'}
    return StreamingResponse(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)


@router.post("/{site_id}/masters/{master_type}/preview")
async def master_preview(site_id: str, master_type: str, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    csrf(request)
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    require_permission(db, user, site_id, "MASTERS", "CREATE")
    key = master_type.upper()
    spec = MASTER_TEMPLATES.get(key)
    if not spec:
        raise HTTPException(404, "Unknown master type.")
    payload = await file.read()
    if len(payload) > 15 * 1024 * 1024:
        raise HTTPException(413, "Master upload exceeds 15 MB.")
    try:
        wb = load_workbook(BytesIO(payload), read_only=True, data_only=False)
        ws = wb[wb.sheetnames[0]]
    except Exception as exc:
        raise HTTPException(422, "Upload a valid .xlsx workbook.") from exc
    headers = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    missing = sorted(spec["required"] - set(headers))
    rows = []
    errors = []
    for row_no, cells in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not any(v not in (None, "") for v in cells):
            continue
        item = {headers[i]: cells[i] for i in range(min(len(headers), len(cells))) if headers[i]}
        row_errors = []
        for required in spec["required"]:
            if item.get(required) in (None, ""):
                row_errors.append(f"{required} is required")
        if row_errors:
            errors.append({"row": row_no, "errors": row_errors})
        rows.append({"row": row_no, "values": item, "errors": row_errors})
    batch_id = f"MIMP-{site_id}-{uuid4().hex[:12].upper()}"
    db.add(MasterImportBatch(
        batch_id=batch_id,
        site_id=site_id,
        master_type=key,
        file_name=file.filename or "upload.xlsx",
        file_hash=sha256(payload).hexdigest(),
        status="PREVIEW" if not missing else "INVALID_HEADERS",
        total_rows=max(0, ws.max_row - 1),
        valid_rows=max(0, ws.max_row - 1 - len(errors)) if not missing else 0,
        update_rows=0,
        error_rows=len(errors) + (1 if missing else 0),
        uploaded_by=user.login_id,
        notes=("Missing headers: " + ", ".join(missing)) if missing else None,
    ))
    for staged in rows:
        db.add(MasterImportRow(
            batch_id=batch_id,
            row_no=staged["row"],
            row_json=json.dumps(staged["values"], default=str),
            status="ERROR" if staged["errors"] or missing else "VALID",
            error_text="; ".join(staged["errors"]) if staged["errors"] else (("Missing headers: " + ", ".join(missing)) if missing else None),
        ))
    _audit(db, user, site_id, "MASTER_IMPORT_PREVIEW", "master_import_batch", batch_id, after={"master": key, "rows": ws.max_row - 1, "missingHeaders": missing, "errors": len(errors)})
    db.commit()
    return {"ok": not missing, "batchId": batch_id, "masterType": key, "headers": headers, "missingHeaders": missing, "totalRows": max(0, ws.max_row - 1), "errorRows": len(errors), "sample": rows[:25], "errors": errors[:100]}


@router.post("/{site_id}/masters/imports/{batch_id}/confirm")
def confirm_master_import(site_id: str, batch_id: str, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    require_permission(db, user, site_id, "MASTERS", "APPROVE")
    batch = db.get(MasterImportBatch, batch_id)
    if not batch or batch.site_id != site_id:
        raise HTTPException(404, "Import batch not found.")
    if batch.status not in {"PREVIEW"}:
        raise HTTPException(409, f"Batch cannot be confirmed from status {batch.status}.")
    staged = list(db.scalars(select(MasterImportRow).where(MasterImportRow.batch_id == batch_id).order_by(MasterImportRow.row_no)))
    if any(r.status == "ERROR" for r in staged):
        raise HTTPException(409, "Fix validation errors and upload a new batch before confirming.")

    created = updated = 0
    for staged_row in staged:
        item = json.loads(staged_row.row_json)
        if batch.master_type == "EMPLOYEE":
            employee_id = str(item["Employee ID"]).strip()
            row = db.get(Person, employee_id)
            is_new = row is None
            if is_new:
                row = Person(employee_id=employee_id, name=str(item["Employee Name"]).strip(), role=str(item["Role"]).strip(), active=_bool(item.get("Active"), True))
                db.add(row)
            else:
                row.name = str(item["Employee Name"]).strip(); row.role = str(item["Role"]).strip(); row.active = _bool(item.get("Active"), row.active)
            row.department = _clean(item.get("Department")); row.mobile = _clean(item.get("Mobile"))
            eff = _date(item.get("Effective From"), date.today())
            assignment = db.scalar(select(PersonSiteAssignment).where(PersonSiteAssignment.employee_id == employee_id, PersonSiteAssignment.site_id == site_id, PersonSiteAssignment.active.is_(True)))
            if not assignment:
                db.add(PersonSiteAssignment(employee_id=employee_id, site_id=site_id, effective_from=eff, primary_site=True, active=row.active, source="BULK_UPLOAD", import_batch_id=batch_id))
            created += int(is_new); updated += int(not is_new)

        elif batch.master_type in {"VEHICLE", "EQUIPMENT"}:
            machine_id = str(item["Machine ID"]).strip()
            row = db.get(Equipment, machine_id)
            is_new = row is None
            group = str(item.get("Group") or ("VEHICLE" if batch.master_type == "VEHICLE" else "EQUIPMENT")).strip()
            if is_new:
                row = Equipment(machine_id=machine_id, type=str(item["Type"]).strip(), group=group, active=_bool(item.get("Active"), True))
                db.add(row)
            else:
                row.type = str(item["Type"]).strip(); row.group = group; row.active = _bool(item.get("Active"), row.active)
            row.door_no = _clean(item.get("Door No")); row.vehicle_no = _clean(item.get("Registration No") or item.get("Vehicle No")); row.make_model = _clean(item.get("Make Model")); row.ownership = _clean(item.get("Ownership"))
            if item.get("Bucket CuM") not in (None, ""): row.bucket_cum = float(item["Bucket CuM"])
            if item.get("Rated Payload T") not in (None, ""): row.rated_payload_t = float(item["Rated Payload T"])
            eff = _date(item.get("Effective From"), date.today())
            assignment = db.scalar(select(EquipmentSiteAssignment).where(EquipmentSiteAssignment.machine_id == machine_id, EquipmentSiteAssignment.site_id == site_id, EquipmentSiteAssignment.active.is_(True)))
            if not assignment:
                db.add(EquipmentSiteAssignment(machine_id=machine_id, site_id=site_id, effective_from=eff, ownership=row.ownership, party=_clean(item.get("Party")), active=row.active, source="BULK_UPLOAD", import_batch_id=batch_id))
            created += int(is_new); updated += int(not is_new)

        elif batch.master_type == "LOCATION":
            code = str(item["Code"]).strip().upper()
            role = str(item.get("Role") or "UNCLASSIFIED").strip().upper()
            if role not in {"UNCLASSIFIED", "SOURCE", "DESTINATION", "BOTH"}:
                raise HTTPException(422, f"Invalid Location Role for {code}: {role}")
            if site_id == "TIOM":
                row = db.get(Location, code); is_new = row is None
                if is_new:
                    row = Location(
                        location_id=code,
                        location_name=str(item["Location Name"]).strip(),
                        location_type=_clean(item.get("Location Type")),
                        role=role,
                        active=_bool(item.get("Active"), True),
                    )
                    db.add(row)
                else:
                    row.location_name = str(item["Location Name"]).strip()
                    row.location_type = _clean(item.get("Location Type"))
                    row.role = role
                    row.active = _bool(item.get("Active"), row.active)
            else:
                key = f"{site_id}:{code}"
                row = db.get(SiteLocation, key); is_new = row is None
                if is_new:
                    row = SiteLocation(site_location_id=key, site_id=site_id, code=code, name=str(item["Location Name"]).strip(), active=_bool(item.get("Active"), True), import_batch_id=batch_id); db.add(row)
                else:
                    row.name = str(item["Location Name"]).strip(); row.active = _bool(item.get("Active"), row.active); row.import_batch_id=batch_id
                row.location_type=_clean(item.get("Location Type")); row.distance_km=Decimal(str(item["Distance KM"])) if item.get("Distance KM") not in (None, "") else None; row.latitude=Decimal(str(item["Latitude"])) if item.get("Latitude") not in (None, "") else None; row.longitude=Decimal(str(item["Longitude"])) if item.get("Longitude") not in (None, "") else None
            created += int(is_new); updated += int(not is_new)

        elif batch.master_type == "MATERIAL":
            code = str(item["Code"]).strip().upper(); key = f"{site_id}:{code}"
            row = db.get(SiteMaterial, key); is_new = row is None
            if is_new:
                row = SiteMaterial(site_material_id=key, site_id=site_id, code=code, name=str(item["Material Name"]).strip(), default_unit=str(item["Default Unit"]).strip().upper(), active=_bool(item.get("Active"), True)); db.add(row)
            else:
                row.name=str(item["Material Name"]).strip(); row.default_unit=str(item["Default Unit"]).strip().upper(); row.active=_bool(item.get("Active"), row.active)
            row.material_group=_clean(item.get("Material Group")); row.billable_unit=_clean(item.get("Billable Unit"));
            if row.billable_unit: row.billable_unit=row.billable_unit.upper()
            created += int(is_new); updated += int(not is_new)
        else:
            raise HTTPException(409, "This master type is not enabled for confirmation yet.")
        staged_row.status = "IMPORTED"

    batch.status = "IMPORTED"; batch.confirmed_by = user.login_id; batch.confirmed_at = datetime.now(timezone.utc); batch.update_rows = updated
    _audit(db, user, site_id, "MASTER_IMPORT_CONFIRM", "master_import_batch", batch_id, after={"created": created, "updated": updated, "rows": len(staged)})
    db.commit()
    return {"ok": True, "batchId": batch_id, "created": created, "updated": updated, "rows": len(staged)}


def _master_type_key(master_type: str) -> str:
    key = str(master_type or "").upper().strip()
    if key not in MASTER_TEMPLATES:
        raise HTTPException(404, "Unknown master type.")
    return key


def _num(value, field: str, allow_none=True):
    if value in (None, "") and allow_none:
        return None
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise HTTPException(422, f"{field} must be numeric.") from exc


def _single_master_save(db: Session, user, site_id: str, key: str, item: dict):
    now = date.today()
    if key == "EMPLOYEE":
        employee_id = str(item.get("employeeId") or "").strip()
        name = str(item.get("name") or "").strip()
        role = str(item.get("role") or "").strip()
        if not employee_id or not name or not role:
            raise HTTPException(422, "Employee ID, name and role are required.")
        row = db.get(Person, employee_id)
        created = row is None
        before = None if created else {"name": row.name, "role": row.role, "department": row.department, "mobile": row.mobile, "active": row.active}
        if row is None:
            row = Person(employee_id=employee_id, name=name, role=role, active=_bool(item.get("active"), True))
            db.add(row)
        row.name = name
        row.role = role
        row.department = _clean(item.get("department"))
        row.mobile = _clean(item.get("mobile"))
        row.active = _bool(item.get("active"), row.active)
        eff = _date(item.get("effectiveFrom"), now)
        assignment = db.scalar(select(PersonSiteAssignment).where(
            PersonSiteAssignment.employee_id == employee_id,
            PersonSiteAssignment.site_id == site_id,
        ).order_by(PersonSiteAssignment.effective_from.desc(), PersonSiteAssignment.id.desc()).limit(1))
        if not assignment:
            assignment = PersonSiteAssignment(employee_id=employee_id, site_id=site_id, effective_from=eff, primary_site=True, active=row.active, source="SINGLE_ENTRY")
            db.add(assignment)
        else:
            assignment.effective_from = eff
            assignment.active = row.active
            assignment.primary_site = _bool(item.get("primarySite"), assignment.primary_site)
            assignment.source = "SINGLE_ENTRY"
        after = {"employeeId": employee_id, "name": row.name, "role": row.role, "department": row.department, "mobile": row.mobile, "effectiveFrom": eff, "active": row.active}
        _audit(db, user, site_id, "MASTER_SINGLE_UPSERT", "employee", employee_id, before=before, after=after)
        return created, after

    if key in {"VEHICLE", "EQUIPMENT"}:
        machine_id = str(item.get("machineId") or "").strip()
        typ = str(item.get("type") or "").strip()
        group = str(item.get("group") or ("VEHICLE" if key == "VEHICLE" else "EQUIPMENT")).strip()
        if not machine_id or not typ or not group:
            raise HTTPException(422, "Machine ID, type and group are required.")
        row = db.get(Equipment, machine_id)
        created = row is None
        before = None if created else {"vehicleNo": row.vehicle_no, "doorNo": row.door_no, "type": row.type, "group": row.group, "ownership": row.ownership, "active": row.active}
        if row is None:
            row = Equipment(machine_id=machine_id, type=typ, group=group, active=_bool(item.get("active"), True))
            db.add(row)
        row.door_no = _clean(item.get("doorNo"))
        row.vehicle_no = _clean(item.get("vehicleNo") or item.get("registrationNo"))
        row.type = typ
        row.group = group
        row.make_model = _clean(item.get("makeModel"))
        row.ownership = _clean(item.get("ownership"))
        row.bucket_cum = float(_num(item.get("bucketCum"), "Bucket CuM")) if item.get("bucketCum") not in (None, "") else None
        row.rated_payload_t = float(_num(item.get("ratedPayloadT"), "Rated Payload T")) if item.get("ratedPayloadT") not in (None, "") else None
        row.active = _bool(item.get("active"), row.active)
        eff = _date(item.get("effectiveFrom"), now)
        assignment = db.scalar(select(EquipmentSiteAssignment).where(
            EquipmentSiteAssignment.machine_id == machine_id,
            EquipmentSiteAssignment.site_id == site_id,
        ).order_by(EquipmentSiteAssignment.effective_from.desc(), EquipmentSiteAssignment.id.desc()).limit(1))
        if not assignment:
            assignment = EquipmentSiteAssignment(machine_id=machine_id, site_id=site_id, effective_from=eff, ownership=row.ownership, party=_clean(item.get("party")), active=row.active, source="SINGLE_ENTRY")
            db.add(assignment)
        else:
            assignment.effective_from = eff
            assignment.ownership = row.ownership
            assignment.party = _clean(item.get("party"))
            assignment.active = row.active
            assignment.source = "SINGLE_ENTRY"
        after = {"machineId": machine_id, "vehicleNo": row.vehicle_no, "doorNo": row.door_no, "type": row.type, "group": row.group, "makeModel": row.make_model, "bucketCum": row.bucket_cum, "ratedPayloadT": row.rated_payload_t, "ownership": row.ownership, "party": assignment.party, "effectiveFrom": eff, "active": row.active}
        _audit(db, user, site_id, "MASTER_SINGLE_UPSERT", "equipment", machine_id, before=before, after=after)
        return created, after

    if key == "LOCATION":
        code = str(item.get("code") or "").upper().strip()
        name = str(item.get("name") or "").strip()
        if not code or not name:
            raise HTTPException(422, "Location code and name are required.")
        role = str(item.get("role") or "UNCLASSIFIED").upper().strip()
        if role not in {"UNCLASSIFIED", "SOURCE", "DESTINATION", "BOTH"}:
            raise HTTPException(422, "Location role must be SOURCE, DESTINATION, BOTH or UNCLASSIFIED.")

        if site_id == "TIOM":
            row = db.get(Location, code)
            created = row is None
            before = None if created else {
                "name": row.location_name, "role": row.role,
                "locationType": row.location_type, "active": row.active,
            }
            if row is None:
                row = Location(
                    location_id=code,
                    location_name=name,
                    location_type=_clean(item.get("locationType")),
                    role=role,
                    active=_bool(item.get("active"), True),
                )
                db.add(row)
            else:
                row.location_name = name
                row.location_type = _clean(item.get("locationType"))
                row.role = role
                row.active = _bool(item.get("active"), row.active)
            after = {
                "recordId": code, "code": code, "name": row.location_name,
                "role": row.role or "UNCLASSIFIED",
                "locationType": row.location_type,
                "distanceKm": None, "latitude": None, "longitude": None,
                "active": row.active,
            }
            _audit(db, user, site_id, "MASTER_SINGLE_UPSERT", "location", code, before=before, after=after)
            return created, after

        record_id = f"{site_id}:{code}"
        row = db.get(SiteLocation, record_id)
        created = row is None
        before = None if created else {"name": row.name, "locationType": row.location_type, "distanceKm": row.distance_km, "latitude": row.latitude, "longitude": row.longitude, "active": row.active}
        if row is None:
            row = SiteLocation(site_location_id=record_id, site_id=site_id, code=code, name=name, active=_bool(item.get("active"), True))
            db.add(row)
        row.name = name
        row.location_type = _clean(item.get("locationType"))
        row.distance_km = _num(item.get("distanceKm"), "Distance KM")
        row.latitude = _num(item.get("latitude"), "Latitude")
        row.longitude = _num(item.get("longitude"), "Longitude")
        row.active = _bool(item.get("active"), row.active)
        after = {"recordId": record_id, "code": code, "name": row.name, "role": "UNCLASSIFIED", "locationType": row.location_type, "distanceKm": row.distance_km, "latitude": row.latitude, "longitude": row.longitude, "active": row.active}
        _audit(db, user, site_id, "MASTER_SINGLE_UPSERT", "site_location", record_id, before=before, after=after)
        return created, after

    if key == "MATERIAL":
        code = str(item.get("code") or "").upper().strip()
        name = str(item.get("name") or "").strip()
        default_unit = str(item.get("defaultUnit") or "").upper().strip()
        if not code or not name or not default_unit:
            raise HTTPException(422, "Material code, name and default unit are required.")
        record_id = f"{site_id}:{code}"
        row = db.get(SiteMaterial, record_id)
        created = row is None
        before = None if created else {"name": row.name, "materialGroup": row.material_group, "defaultUnit": row.default_unit, "billableUnit": row.billable_unit, "active": row.active}
        if row is None:
            row = SiteMaterial(site_material_id=record_id, site_id=site_id, code=code, name=name, default_unit=default_unit, active=_bool(item.get("active"), True))
            db.add(row)
        row.name = name
        row.material_group = _clean(item.get("materialGroup"))
        row.default_unit = default_unit
        row.billable_unit = _clean(item.get("billableUnit"))
        if row.billable_unit:
            row.billable_unit = row.billable_unit.upper()
        row.active = _bool(item.get("active"), row.active)
        after = {"recordId": record_id, "code": code, "name": row.name, "materialGroup": row.material_group, "defaultUnit": row.default_unit, "billableUnit": row.billable_unit, "active": row.active}
        _audit(db, user, site_id, "MASTER_SINGLE_UPSERT", "site_material", record_id, before=before, after=after)
        return created, after

    raise HTTPException(404, "Unknown master type.")


@router.get("/{site_id}/masters/{master_type}/records")
def list_master_records(site_id: str, master_type: str, request: Request, active_only: bool = False, limit: int = 250, db: Session = Depends(get_db)):
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    if not user.admin and not (has_permission(db, user, site_id, "MASTERS", "VIEW") or has_permission(db, user, site_id, "MASTERS", "EDIT")):
        raise HTTPException(403, "Master view permission is required.")
    key = _master_type_key(master_type)
    limit = min(max(int(limit), 1), 1000)

    if key == "EMPLOYEE":
        stmt = select(Person, PersonSiteAssignment).join(PersonSiteAssignment, PersonSiteAssignment.employee_id == Person.employee_id).where(PersonSiteAssignment.site_id == site_id)
        if active_only:
            stmt = stmt.where(PersonSiteAssignment.active.is_(True), Person.active.is_(True))
        rows = db.execute(stmt.order_by(Person.employee_id).limit(limit)).all()
        return [{"employeeId": p.employee_id, "name": p.name, "role": p.role, "department": p.department, "mobile": p.mobile, "effectiveFrom": a.effective_from, "primarySite": a.primary_site, "active": bool(p.active and a.active)} for p, a in rows]

    if key in {"VEHICLE", "EQUIPMENT"}:
        stmt = select(Equipment, EquipmentSiteAssignment).join(EquipmentSiteAssignment, EquipmentSiteAssignment.machine_id == Equipment.machine_id).where(EquipmentSiteAssignment.site_id == site_id)
        if key == "VEHICLE":
            stmt = stmt.where(Equipment.group == "VEHICLE")
        if active_only:
            stmt = stmt.where(EquipmentSiteAssignment.active.is_(True), Equipment.active.is_(True))
        rows = db.execute(stmt.order_by(Equipment.machine_id).limit(limit)).all()
        return [{"machineId": e.machine_id, "vehicleNo": e.vehicle_no, "doorNo": e.door_no, "type": e.type, "group": e.group, "makeModel": e.make_model, "bucketCum": e.bucket_cum, "ratedPayloadT": e.rated_payload_t, "ownership": e.ownership, "party": a.party, "effectiveFrom": a.effective_from, "active": bool(e.active and a.active)} for e, a in rows]

    if key == "LOCATION":
        if site_id == "TIOM":
            stmt = select(Location)
            if active_only:
                stmt = stmt.where(Location.active.is_(True))
            rows = db.scalars(stmt.order_by(Location.location_id).limit(limit)).all()
            return [{
                "recordId": x.location_id,
                "code": x.location_id,
                "name": x.location_name,
                "role": (x.role or "UNCLASSIFIED"),
                "locationType": x.location_type,
                "distanceKm": None,
                "latitude": None,
                "longitude": None,
                "active": x.active,
            } for x in rows]
        stmt = select(SiteLocation).where(SiteLocation.site_id == site_id)
        if active_only:
            stmt = stmt.where(SiteLocation.active.is_(True))
        rows = db.scalars(stmt.order_by(SiteLocation.code).limit(limit)).all()
        return [{"recordId": x.site_location_id, "code": x.code, "name": x.name, "role": "UNCLASSIFIED", "locationType": x.location_type, "distanceKm": x.distance_km, "latitude": x.latitude, "longitude": x.longitude, "active": x.active} for x in rows]

    stmt = select(SiteMaterial).where(SiteMaterial.site_id == site_id)
    if active_only:
        stmt = stmt.where(SiteMaterial.active.is_(True))
    rows = db.scalars(stmt.order_by(SiteMaterial.code).limit(limit)).all()
    return [{"recordId": x.site_material_id, "code": x.code, "name": x.name, "materialGroup": x.material_group, "defaultUnit": x.default_unit, "billableUnit": x.billable_unit, "active": x.active} for x in rows]


@router.post("/{site_id}/masters/{master_type}/records")
def save_single_master_record(site_id: str, master_type: str, payload: dict, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    key = _master_type_key(master_type)
    # CREATE allows first entry; EDIT allows subsequent maintenance. Admin bypasses both.
    if not user.admin and not (has_permission(db, user, site_id, "MASTERS", "CREATE") or has_permission(db, user, site_id, "MASTERS", "EDIT")):
        raise HTTPException(403, "Master create/edit permission is required.")
    created, record = _single_master_save(db, user, site_id, key, payload or {})
    db.commit()
    return {"ok": True, "created": created, "masterType": key, "record": record}


@router.get("/{site_id}/weight-factors")
def get_weight_factors(site_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    if not user.admin and not has_permission(db, user, site_id, "MCL_FACTOR", "VIEW"):
        raise HTTPException(403, "Factor view permission is required.")
    rows = db.scalars(select(SiteWeightFactor).where(SiteWeightFactor.site_id == site_id).order_by(SiteWeightFactor.effective_from.desc(), SiteWeightFactor.entered_at.desc())).all()
    return [{
        "factorId": r.factor_id,
        "factorType": r.factor_type,
        "factorValue": r.factor_value,
        "factorUnit": r.factor_unit,
        "operatingDate": r.operating_date,
        "shift": r.shift,
        "vehicleClass": r.vehicle_class,
        "effectiveFrom": r.effective_from,
        "effectiveTo": r.effective_to,
        "sourceOrg": r.source_org,
        "referenceNo": r.reference_no,
        "status": r.status,
        "version": r.version,
    } for r in rows]


@router.post("/{site_id}/weight-factors")
def create_weight_factor(site_id: str, p: WeightFactorIn, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    require_permission(db, user, site_id, "MCL_FACTOR", "CREATE")
    if site_id != "KOCP" and p.sourceOrg.upper() == "MCL":
        raise HTTPException(409, "MCL factor workflow is currently configured for KOCP.")
    factor_id = f"FAC-{site_id}-{uuid4().hex[:12].upper()}"
    row = SiteWeightFactor(
        factor_id=factor_id,
        site_id=site_id,
        factor_type=p.factorType.upper(),
        factor_value=p.factorValue,
        factor_unit=p.factorUnit.upper(),
        effective_from=p.effectiveFrom,
        effective_to=p.effectiveTo,
        operating_date=p.operatingDate,
        shift=p.shift.upper() if p.shift else None,
        material_id=p.materialId,
        vehicle_class=p.vehicleClass,
        source_org=p.sourceOrg,
        reference_no=p.referenceNo,
        reference_date=p.referenceDate,
        status="DRAFT",
        entered_by=user.login_id,
        notes=p.notes,
    )
    db.add(row)
    _audit(db, user, site_id, "CREATE_FACTOR", "site_weight_factor", factor_id, after=p.model_dump())
    db.commit()
    return {"ok": True, "factorId": factor_id, "status": "DRAFT"}


@router.post("/{site_id}/weight-factors/{factor_id}/decision")
def decide_weight_factor(site_id: str, factor_id: str, p: WeightFactorDecisionIn, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    require_permission(db, user, site_id, "MCL_FACTOR", "APPROVE")
    row = db.get(SiteWeightFactor, factor_id)
    if not row or row.site_id != site_id:
        raise HTTPException(404, "Factor not found.")
    before = {"status": row.status, "approvedBy": row.approved_by}
    row.status = "APPROVED" if p.action == "APPROVE" else "REJECTED"
    row.approved_by = user.login_id if p.action == "APPROVE" else None
    row.approved_at = datetime.now(timezone.utc) if p.action == "APPROVE" else None
    _audit(db, user, site_id, p.action + "_FACTOR", "site_weight_factor", factor_id, before=before, after={"status": row.status}, reason=p.reason)
    db.commit()
    return {"ok": True, "factorId": factor_id, "status": row.status}


@router.post("/{site_id}/wb/manual")
def save_manual_wb(site_id: str, p: SiteWbManualIn, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    require_permission(db, user, site_id, "WB", "CREATE")
    if db.scalar(select(SiteWbMovement.movement_key).where(SiteWbMovement.site_id == site_id, SiteWbMovement.wb_id == p.wbId)):
        raise HTTPException(409, "This WB ID is already recorded for the site.")
    ctx = resolve_site_context(db, site_id, p.weighAt)
    movement_key = f"{site_id}:WB:{p.wbId}"
    row = SiteWbMovement(
        movement_key=movement_key,
        site_id=site_id,
        operating_date=ctx.operating_date,
        shift=ctx.shift,
        wb_id=p.wbId,
        weigh_at=p.weighAt,
        vehicle_raw=p.vehicleRegNo.upper().replace(" ", ""),
        party=p.party,
        source_raw=p.source,
        destination_raw=p.destination,
        gross_kg=p.grossKg,
        tare_kg=p.tareKg,
        net_kg=p.netKg,
        row_status="VALID",
        entered_by=user.login_id,
    )
    db.add(row)
    _audit(db, user, site_id, "CREATE_WB", "site_wb_movement", movement_key, after={"wbId": p.wbId, "operatingDate": ctx.operating_date, "shift": ctx.shift, "netKg": str(p.netKg)})
    db.commit()
    return {"ok": True, "movementKey": movement_key, "operatingDate": ctx.operating_date, "shift": ctx.shift}


@router.post("/{site_id}/trips")
def create_site_trip(site_id: str, p: SiteTripIn, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    if not user.admin and not (has_permission(db, user, site_id, "TRIP", "CREATE") or (site_id == "KOCP" and has_permission(db, user, site_id, "OB", "CREATE"))):
        raise HTTPException(403, "TRIP/OB create permission is required for this site.")
    event_at = p.eventAt or p.loadingStartAt or datetime.now(timezone.utc)
    ctx = resolve_site_context(db, site_id, event_at)
    if p.sourceRecordUid:
        existing = db.scalar(select(SiteTrip.trip_id).where(SiteTrip.site_id == site_id, SiteTrip.source_type == p.sourceType, SiteTrip.source_record_uid == p.sourceRecordUid))
        if existing:
            return {"ok": True, "tripId": existing, "idempotent": True}
    quantity_mt = p.quantityMt
    quantity_cum = p.quantityCum
    weight_basis = p.weightBasis
    if p.factorId:
        factor = db.get(SiteWeightFactor, p.factorId)
        if not factor or factor.site_id != site_id or factor.status != "APPROVED":
            raise HTTPException(409, "Selected factor is not an approved factor for this site.")
        if ctx.operating_date < factor.effective_from or (factor.effective_to and ctx.operating_date > factor.effective_to):
            raise HTTPException(409, "Selected factor is outside its effective date range.")
        if factor.operating_date and factor.operating_date != ctx.operating_date:
            raise HTTPException(409, "Selected factor is for a different operating date.")
        if factor.shift and factor.shift != ctx.shift:
            raise HTTPException(409, "Selected factor is for a different shift.")
        if factor.factor_type == "COAL_AVG_MT_PER_TRIP":
            quantity_mt = factor.factor_value
            weight_basis = "MCL_SHIFT_AVERAGE"
        elif factor.factor_type == "OB_CUM_PER_TRIP":
            quantity_cum = factor.factor_value
            weight_basis = "MCL_DUMPER_FACTOR"

    trip_id = f"TRIP-{site_id}-{uuid4().hex[:14].upper()}"
    row = SiteTrip(
        trip_id=trip_id,
        site_id=site_id,
        operating_date=ctx.operating_date,
        shift=ctx.shift,
        event_at=event_at,
        vehicle_id=p.vehicleId,
        vehicle_raw=p.vehicleRaw,
        driver_id=p.driverId,
        loading_equipment_id=p.loadingEquipmentId,
        loading_operator_id=p.loadingOperatorId,
        source_location_id=p.sourceLocationId,
        destination_location_id=p.destinationLocationId,
        material_id=p.materialId,
        gp_no=p.gpNo,
        trip_seq=p.tripSeq,
        loading_start_at=p.loadingStartAt,
        loading_end_at=p.loadingEndAt,
        unloading_start_at=p.unloadingStartAt,
        unloading_end_at=p.unloadingEndAt,
        quantity_mt=quantity_mt,
        quantity_cum=quantity_cum,
        weight_basis=weight_basis,
        factor_id=p.factorId,
        source_type=p.sourceType,
        source_record_uid=p.sourceRecordUid,
        status="POSTED",
        entered_by=user.login_id,
    )
    db.add(row)
    _audit(db, user, site_id, "CREATE_TRIP", "site_trip", trip_id, after={"operatingDate": ctx.operating_date, "shift": ctx.shift, "vehicle": p.vehicleId or p.vehicleRaw, "quantityMt": str(quantity_mt) if quantity_mt is not None else None, "quantityCum": str(quantity_cum) if quantity_cum is not None else None})
    db.commit()
    return {"ok": True, "tripId": trip_id, "operatingDate": ctx.operating_date, "shift": ctx.shift}



@router.get("/{site_id}/records/trips")
def list_site_trips(site_id: str, request: Request, operating_date: date | None = None, limit: int = 100, db: Session = Depends(get_db)):
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    if not user.admin and not any(has_permission(db, user, site_id, m, "VIEW") for m in ("TRIP", "OB", "PRODUCTION", "FIELD_ENTRY")):
        raise HTTPException(403, "Trip view permission is required.")
    limit = max(1, min(int(limit), 500))
    stmt = select(SiteTrip).where(SiteTrip.site_id == site_id)
    if operating_date:
        stmt = stmt.where(SiteTrip.operating_date == operating_date)
    rows = db.scalars(stmt.order_by(SiteTrip.entered_at.desc()).limit(limit)).all()
    return [{
        "tripId": r.trip_id, "operatingDate": r.operating_date, "shift": r.shift,
        "eventAt": r.event_at, "vehicleId": r.vehicle_id, "vehicleRaw": r.vehicle_raw,
        "driverId": r.driver_id, "loadingEquipmentId": r.loading_equipment_id,
        "sourceLocationId": r.source_location_id, "destinationLocationId": r.destination_location_id,
        "materialId": r.material_id, "gpNo": r.gp_no, "quantityMt": r.quantity_mt,
        "quantityCum": r.quantity_cum, "weightBasis": r.weight_basis, "status": r.status,
        "enteredBy": r.entered_by, "enteredAt": r.entered_at,
    } for r in rows]


@router.get("/{site_id}/records/wb")
def list_site_wb(site_id: str, request: Request, operating_date: date | None = None, limit: int = 100, db: Session = Depends(get_db)):
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    if not user.admin and not has_permission(db, user, site_id, "WB", "VIEW"):
        raise HTTPException(403, "WB view permission is required.")
    limit = max(1, min(int(limit), 500))
    stmt = select(SiteWbMovement).where(SiteWbMovement.site_id == site_id)
    if operating_date:
        stmt = stmt.where(SiteWbMovement.operating_date == operating_date)
    rows = db.scalars(stmt.order_by(SiteWbMovement.weigh_at.desc()).limit(limit)).all()
    return [{
        "wbId": r.wb_id, "operatingDate": r.operating_date, "shift": r.shift,
        "weighAt": r.weigh_at, "vehicle": r.vehicle_raw, "party": r.party,
        "source": r.source_raw, "destination": r.destination_raw,
        "grossKg": r.gross_kg, "tareKg": r.tare_kg, "netKg": r.net_kg,
        "status": r.row_status, "issue": r.issue, "enteredBy": r.entered_by,
    } for r in rows]


@router.get("/{site_id}/records/hsd")
def list_site_hsd(site_id: str, request: Request, operating_date: date | None = None, limit: int = 100, db: Session = Depends(get_db)):
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    if not user.admin and not has_permission(db, user, site_id, "HSD", "VIEW"):
        raise HTTPException(403, "HSD view permission is required.")
    limit = max(1, min(int(limit), 500))
    stmt = select(SiteHsdTransaction).where(SiteHsdTransaction.site_id == site_id)
    if operating_date:
        stmt = stmt.where(SiteHsdTransaction.operating_date == operating_date)
    rows = db.scalars(stmt.order_by(SiteHsdTransaction.entered_at.desc()).limit(limit)).all()
    return [{
        "transactionId": r.transaction_id, "operatingDate": r.operating_date, "shift": r.shift,
        "transactionType": r.transaction_type, "assetType": r.asset_type, "assetId": r.asset_id,
        "litres": r.litres, "supplier": r.supplier, "referenceNo": r.reference_no,
        "meterReading": r.meter_reading, "eventAt": r.event_at, "status": r.status,
        "enteredBy": r.entered_by, "enteredAt": r.entered_at,
    } for r in rows]


@router.get("/{site_id}/master-summary")
def site_master_summary(site_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    if not user.admin and not has_permission(db, user, site_id, "MASTERS", "VIEW"):
        raise HTTPException(403, "Master view permission is required.")
    employee_count = db.scalar(select(func.count()).select_from(PersonSiteAssignment).where(PersonSiteAssignment.site_id == site_id, PersonSiteAssignment.active.is_(True))) or 0
    equipment_count = db.scalar(select(func.count()).select_from(EquipmentSiteAssignment).where(EquipmentSiteAssignment.site_id == site_id, EquipmentSiteAssignment.active.is_(True))) or 0
    location_count = db.scalar(select(func.count()).select_from(SiteLocation).where(SiteLocation.site_id == site_id, SiteLocation.active.is_(True))) or 0
    material_count = db.scalar(select(func.count()).select_from(SiteMaterial).where(SiteMaterial.site_id == site_id, SiteMaterial.active.is_(True))) or 0
    imports = db.scalars(select(MasterImportBatch).where(MasterImportBatch.site_id == site_id).order_by(MasterImportBatch.uploaded_at.desc()).limit(25)).all()
    return {"employees": employee_count, "equipment": equipment_count, "locations": location_count, "materials": material_count,
            "imports": [{"batchId": x.batch_id, "masterType": x.master_type, "fileName": x.file_name, "status": x.status, "totalRows": x.total_rows, "errorRows": x.error_rows, "uploadedBy": x.uploaded_by, "uploadedAt": x.uploaded_at} for x in imports]}


@router.get("/{site_id}/audit")
def site_audit(site_id: str, request: Request, limit: int = 100, db: Session = Depends(get_db)):
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    if not user.admin and not has_permission(db, user, site_id, "AUDIT", "VIEW"):
        raise HTTPException(403, "Audit view permission is required.")
    limit = max(1, min(int(limit), 500))
    rows = db.scalars(select(SiteAuditLog).where(SiteAuditLog.site_id == site_id).order_by(SiteAuditLog.created_at.desc()).limit(limit)).all()
    return [{"createdAt": r.created_at, "actor": r.actor, "action": r.action, "entity": r.entity, "entityId": r.entity_id, "reason": r.reason} for r in rows]


@router.post("/{site_id}/hsd")
def create_hsd_transaction(site_id: str, p: SiteHsdTransactionIn, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    user = get_user(db, request)
    site_id = require_site(db, user, site_id)
    require_permission(db, user, site_id, "HSD", "CREATE")
    if p.sourceRecordUid:
        existing = db.scalar(select(SiteHsdTransaction.transaction_id).where(SiteHsdTransaction.site_id == site_id, SiteHsdTransaction.source_type == p.sourceType, SiteHsdTransaction.source_record_uid == p.sourceRecordUid))
        if existing:
            return {"ok": True, "transactionId": existing, "idempotent": True}
    tx_id = f"HSD-{site_id}-{uuid4().hex[:14].upper()}"
    row = SiteHsdTransaction(
        transaction_id=tx_id,
        site_id=site_id,
        operating_date=p.operatingDate,
        shift=p.shift,
        transaction_type=p.transactionType,
        asset_type=p.assetType,
        asset_id=p.assetId,
        litres=p.litres,
        supplier=p.supplier,
        reference_no=p.referenceNo,
        meter_reading=p.meterReading,
        event_at=p.eventAt,
        source_type=p.sourceType,
        source_record_uid=p.sourceRecordUid,
        entered_by=user.login_id,
        status="POSTED",
    )
    db.add(row)
    _audit(db, user, site_id, "CREATE_HSD", "site_hsd_transaction", tx_id, after={"type": p.transactionType, "litres": str(p.litres), "asset": p.assetId})
    db.commit()
    return {"ok": True, "transactionId": tx_id}
