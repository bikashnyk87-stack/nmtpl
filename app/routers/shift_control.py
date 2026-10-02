from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Person, Equipment, Location, ShiftMaster,
    PersonAttendance, EquipmentAttendance, ShiftCrew, ShiftDeployment, ShiftState,
)
from app.schemas import (
    PersonAttendanceIn, EquipmentAttendanceIn, ShiftCrewAssignIn,
    ShiftDeploymentAssignIn, ShiftStateIn,
)
from app.services.time_context import now_local

router = APIRouter(prefix="/api/shift-control", tags=["shift-control"])


def _shift(value: str) -> str:
    return value.strip().upper()


def _require_shift(db: Session, shift: str):
    if db.get(ShiftMaster, shift) is None:
        raise HTTPException(422, f"Unknown shift: {shift}")


def _shift_is_closed(db: Session, operating_date, shift: str) -> bool:
    row = db.execute(select(ShiftState).where(
        ShiftState.operating_date == operating_date,
        ShiftState.shift == shift,
    )).scalar_one_or_none()
    return bool(row and row.status == "CLOSED")


def _ensure_open(db: Session, operating_date, shift: str):
    if _shift_is_closed(db, operating_date, shift):
        raise HTTPException(409, f"Shift {operating_date} {shift} is CLOSED")


def _person_attendance_dict(r: PersonAttendance):
    return {
        "id": r.id, "operating_date": r.operating_date, "shift": r.shift,
        "employee_id": r.employee_id, "attendance": r.status,
        "in_at": r.in_at, "out_at": r.out_at,
        "worked_hours": r.worked_hours, "out_source": r.out_source,
        "review_status": r.review_status, "remarks": r.remarks,
        "entered_by": r.entered_by, "entered_at": r.entered_at,
    }


def _equipment_attendance_dict(r: EquipmentAttendance):
    return {
        "id": r.id, "operating_date": r.operating_date, "shift": r.shift,
        "machine_id": r.machine_id, "attendance": r.status,
        "condition": r.condition, "meter_type": r.meter_type,
        "opening_meter": r.opening_meter, "closing_meter": r.closing_meter,
        "run_meter": r.run_meter, "remarks": r.remarks,
        "entered_by": r.entered_by, "entered_at": r.entered_at,
    }


@router.get("/person-attendance")
def get_person_attendance(
    operating_date: str = Query(...), shift: str = Query(...), db: Session = Depends(get_db)
):
    from datetime import date
    try:
        day = date.fromisoformat(operating_date)
    except ValueError:
        raise HTTPException(422, "operating_date must be YYYY-MM-DD")
    sh = _shift(shift)
    rows = db.execute(select(PersonAttendance).where(
        PersonAttendance.operating_date == day, PersonAttendance.shift == sh
    ).order_by(PersonAttendance.employee_id)).scalars().all()
    return [_person_attendance_dict(r) for r in rows]


@router.post("/person-attendance")
def upsert_person_attendance(p: PersonAttendanceIn, db: Session = Depends(get_db)):
    sh = _shift(p.shift)
    _require_shift(db, sh); _ensure_open(db, p.operating_date, sh)
    if db.get(Person, p.employee_id) is None:
        raise HTTPException(404, "Employee not found")
    status = p.attendance.strip().upper()
    now = now_local()
    row = db.execute(select(PersonAttendance).where(
        PersonAttendance.operating_date == p.operating_date,
        PersonAttendance.shift == sh,
        PersonAttendance.employee_id == p.employee_id,
    )).scalar_one_or_none()
    if row is None:
        row = PersonAttendance(
            operating_date=p.operating_date, shift=sh, employee_id=p.employee_id,
            status=status,
        )
    row.status = status
    row.in_at = p.in_at
    row.out_at = p.out_at
    if p.in_at and p.out_at:
        hours = (p.out_at - p.in_at).total_seconds() / 3600
        row.worked_hours = Decimal(str(round(max(hours, 0), 2)))
    else:
        row.worked_hours = None
    row.out_source = p.out_source
    row.review_status = p.review_status
    row.remarks = p.remarks
    row.entered_by = p.entered_by
    row.entered_at = now
    db.add(row); db.commit(); db.refresh(row)
    return {"ok": True, **_person_attendance_dict(row)}


@router.get("/equipment-attendance")
def get_equipment_attendance(
    operating_date: str = Query(...), shift: str = Query(...), db: Session = Depends(get_db)
):
    from datetime import date
    try:
        day = date.fromisoformat(operating_date)
    except ValueError:
        raise HTTPException(422, "operating_date must be YYYY-MM-DD")
    sh = _shift(shift)
    rows = db.execute(select(EquipmentAttendance).where(
        EquipmentAttendance.operating_date == day, EquipmentAttendance.shift == sh
    ).order_by(EquipmentAttendance.machine_id)).scalars().all()
    return [_equipment_attendance_dict(r) for r in rows]


@router.post("/equipment-attendance")
def upsert_equipment_attendance(p: EquipmentAttendanceIn, db: Session = Depends(get_db)):
    sh = _shift(p.shift)
    _require_shift(db, sh); _ensure_open(db, p.operating_date, sh)
    if db.get(Equipment, p.machine_id) is None:
        raise HTTPException(404, "Equipment not found")
    status = p.attendance.strip().upper()
    condition = p.condition.strip().upper() if p.condition else None
    meter_type = p.meter_type.strip().upper() if p.meter_type else None
    now = now_local()
    row = db.execute(select(EquipmentAttendance).where(
        EquipmentAttendance.operating_date == p.operating_date,
        EquipmentAttendance.shift == sh,
        EquipmentAttendance.machine_id == p.machine_id,
    )).scalar_one_or_none()
    if row is None:
        row = EquipmentAttendance(
            operating_date=p.operating_date, shift=sh, machine_id=p.machine_id,
            status=status,
        )
    row.status = status; row.condition = condition; row.meter_type = meter_type
    row.opening_meter = p.opening_meter; row.closing_meter = p.closing_meter
    if p.opening_meter is not None and p.closing_meter is not None:
        row.run_meter = max(p.closing_meter - p.opening_meter, Decimal("0"))
    else:
        row.run_meter = None
    row.remarks = p.remarks; row.entered_by = p.entered_by; row.entered_at = now
    db.add(row); db.commit(); db.refresh(row)
    return {"ok": True, **_equipment_attendance_dict(row)}


@router.get("/crew")
def get_crew(operating_date: str, shift: str, active_only: bool = True, db: Session = Depends(get_db)):
    from datetime import date
    try: day = date.fromisoformat(operating_date)
    except ValueError: raise HTTPException(422, "operating_date must be YYYY-MM-DD")
    sh = _shift(shift)
    q = select(ShiftCrew).where(ShiftCrew.operating_date == day, ShiftCrew.shift == sh)
    if active_only: q = q.where(ShiftCrew.status == "ACTIVE")
    rows = db.execute(q.order_by(ShiftCrew.machine_id, ShiftCrew.from_at)).scalars().all()
    return [{
        "id": r.id, "operating_date": r.operating_date, "shift": r.shift,
        "employee_id": r.employee_id, "machine_id": r.machine_id,
        "from_at": r.from_at, "to_at": r.to_at, "status": r.status,
        "reason": r.reason, "changed_by": r.changed_by, "changed_at": r.changed_at,
    } for r in rows]


@router.post("/crew/assign")
def assign_crew(p: ShiftCrewAssignIn, db: Session = Depends(get_db)):
    sh = _shift(p.shift); _require_shift(db, sh); _ensure_open(db, p.operating_date, sh)
    if db.get(Person, p.employee_id) is None: raise HTTPException(404, "Employee not found")
    if db.get(Equipment, p.machine_id) is None: raise HTTPException(404, "Equipment not found")

    pa = db.execute(select(PersonAttendance).where(
        PersonAttendance.operating_date == p.operating_date,
        PersonAttendance.shift == sh,
        PersonAttendance.employee_id == p.employee_id,
    )).scalar_one_or_none()
    if pa and pa.status != "PRESENT":
        raise HTTPException(409, f"Employee attendance is {pa.status}")
    ea = db.execute(select(EquipmentAttendance).where(
        EquipmentAttendance.operating_date == p.operating_date,
        EquipmentAttendance.shift == sh,
        EquipmentAttendance.machine_id == p.machine_id,
    )).scalar_one_or_none()
    if ea and (ea.status != "PRESENT" or ea.condition == "BREAKDOWN"):
        raise HTTPException(409, f"Equipment is {ea.status}/{ea.condition or ''}")

    now = p.from_at or now_local()
    existing = db.execute(select(ShiftCrew).where(
        ShiftCrew.operating_date == p.operating_date, ShiftCrew.shift == sh,
        ShiftCrew.employee_id == p.employee_id, ShiftCrew.machine_id == p.machine_id,
        ShiftCrew.status == "ACTIVE",
    )).scalar_one_or_none()
    if existing:
        return {"ok": True, "id": existing.id, "status": existing.status, "idempotent": True}

    active = db.execute(select(ShiftCrew).where(
        ShiftCrew.operating_date == p.operating_date, ShiftCrew.shift == sh,
        ShiftCrew.status == "ACTIVE",
        ((ShiftCrew.employee_id == p.employee_id) | (ShiftCrew.machine_id == p.machine_id)),
    )).scalars().all()
    for old in active:
        old.to_at = now; old.status = "CLOSED"; old.reason = "Reassigned"
        old.changed_by = p.changed_by; old.changed_at = now
    row = ShiftCrew(
        operating_date=p.operating_date, shift=sh, employee_id=p.employee_id,
        machine_id=p.machine_id, from_at=now, status="ACTIVE",
        reason=p.reason, changed_by=p.changed_by, changed_at=now,
    )
    db.add(row); db.commit(); db.refresh(row)
    return {"ok": True, "id": row.id, "status": row.status}


@router.post("/crew/{crew_id}/close")
def close_crew(crew_id: int, reason: str = "Closed", changed_by: str = "admin", db: Session = Depends(get_db)):
    row = db.get(ShiftCrew, crew_id)
    if not row: raise HTTPException(404, "Crew assignment not found")
    if row.status == "ACTIVE":
        now = now_local(); row.to_at = now; row.status = "CLOSED"
        row.reason = reason; row.changed_by = changed_by; row.changed_at = now; db.commit()
    return {"ok": True, "id": row.id, "status": row.status}


@router.get("/deployment")
def get_deployment(operating_date: str, shift: str, active_only: bool = True, db: Session = Depends(get_db)):
    from datetime import date
    try: day = date.fromisoformat(operating_date)
    except ValueError: raise HTTPException(422, "operating_date must be YYYY-MM-DD")
    sh = _shift(shift)
    q = select(ShiftDeployment).where(ShiftDeployment.operating_date == day, ShiftDeployment.shift == sh)
    if active_only: q = q.where(ShiftDeployment.status == "ACTIVE")
    rows = db.execute(q.order_by(ShiftDeployment.machine_id, ShiftDeployment.from_at)).scalars().all()
    return [{
        "id": r.id, "operating_date": r.operating_date, "shift": r.shift,
        "machine_id": r.machine_id, "location_id": r.location_id,
        "from_at": r.from_at, "to_at": r.to_at, "status": r.status,
        "reason": r.reason, "changed_by": r.changed_by, "changed_at": r.changed_at,
    } for r in rows]


@router.post("/deployment/assign")
def assign_deployment(p: ShiftDeploymentAssignIn, db: Session = Depends(get_db)):
    sh = _shift(p.shift); _require_shift(db, sh); _ensure_open(db, p.operating_date, sh)
    if db.get(Equipment, p.machine_id) is None: raise HTTPException(404, "Equipment not found")
    if db.get(Location, p.location_id) is None: raise HTTPException(404, "Location not found")
    now = p.from_at or now_local()
    existing = db.execute(select(ShiftDeployment).where(
        ShiftDeployment.operating_date == p.operating_date, ShiftDeployment.shift == sh,
        ShiftDeployment.machine_id == p.machine_id, ShiftDeployment.location_id == p.location_id,
        ShiftDeployment.status == "ACTIVE",
    )).scalar_one_or_none()
    if existing:
        return {"ok": True, "id": existing.id, "status": existing.status, "idempotent": True}
    active = db.execute(select(ShiftDeployment).where(
        ShiftDeployment.operating_date == p.operating_date, ShiftDeployment.shift == sh,
        ShiftDeployment.machine_id == p.machine_id, ShiftDeployment.status == "ACTIVE",
    )).scalars().all()
    for old in active:
        old.to_at = now; old.status = "CLOSED"; old.reason = "Reassigned"
        old.changed_by = p.changed_by; old.changed_at = now
    row = ShiftDeployment(
        operating_date=p.operating_date, shift=sh, machine_id=p.machine_id,
        location_id=p.location_id, from_at=now, status="ACTIVE",
        reason=p.reason, changed_by=p.changed_by, changed_at=now,
    )
    db.add(row); db.commit(); db.refresh(row)
    return {"ok": True, "id": row.id, "status": row.status}


@router.post("/deployment/{deployment_id}/close")
def close_deployment(deployment_id: int, reason: str = "Closed", changed_by: str = "admin", db: Session = Depends(get_db)):
    row = db.get(ShiftDeployment, deployment_id)
    if not row: raise HTTPException(404, "Deployment not found")
    if row.status == "ACTIVE":
        now = now_local(); row.to_at = now; row.status = "CLOSED"
        row.reason = reason; row.changed_by = changed_by; row.changed_at = now; db.commit()
    return {"ok": True, "id": row.id, "status": row.status}


@router.get("/state")
def get_shift_state(operating_date: str, shift: str, db: Session = Depends(get_db)):
    from datetime import date
    try: day = date.fromisoformat(operating_date)
    except ValueError: raise HTTPException(422, "operating_date must be YYYY-MM-DD")
    sh = _shift(shift); _require_shift(db, sh)
    row = db.execute(select(ShiftState).where(
        ShiftState.operating_date == day, ShiftState.shift == sh
    )).scalar_one_or_none()
    if not row:
        return {"operating_date": day, "shift": sh, "status": "OPEN", "implicit": True}
    return {
        "operating_date": row.operating_date, "shift": row.shift, "status": row.status,
        "reason": row.reason, "changed_by": row.changed_by, "changed_at": row.changed_at,
    }


@router.post("/state")
def set_shift_state(p: ShiftStateIn, db: Session = Depends(get_db)):
    sh = _shift(p.shift); _require_shift(db, sh)
    status = p.status.strip().upper()
    if status not in {"OPEN", "CLOSED"}:
        raise HTTPException(422, "status must be OPEN or CLOSED")
    now = now_local()
    row = db.execute(select(ShiftState).where(
        ShiftState.operating_date == p.operating_date, ShiftState.shift == sh
    )).scalar_one_or_none()
    if not row:
        row = ShiftState(operating_date=p.operating_date, shift=sh)
    row.status = status; row.reason = p.reason; row.changed_by = p.changed_by; row.changed_at = now
    db.add(row)
    closed_crew = 0
    closed_deployments = 0
    if status == "CLOSED":
        active_crew = db.execute(select(ShiftCrew).where(
            ShiftCrew.operating_date == p.operating_date, ShiftCrew.shift == sh, ShiftCrew.status == "ACTIVE"
        )).scalars().all()
        for x in active_crew:
            x.to_at = now; x.status = "CLOSED"; x.reason = p.reason or "Shift closed"
            x.changed_by = p.changed_by; x.changed_at = now; closed_crew += 1
        active_dep = db.execute(select(ShiftDeployment).where(
            ShiftDeployment.operating_date == p.operating_date, ShiftDeployment.shift == sh, ShiftDeployment.status == "ACTIVE"
        )).scalars().all()
        for x in active_dep:
            x.to_at = now; x.status = "CLOSED"; x.reason = p.reason or "Shift closed"
            x.changed_by = p.changed_by; x.changed_at = now; closed_deployments += 1
    db.commit(); db.refresh(row)
    return {
        "ok": True, "operating_date": row.operating_date, "shift": row.shift, "status": row.status,
        "closed_crew": closed_crew, "closed_deployments": closed_deployments,
    }


@router.get("/summary")
def shift_summary(operating_date: str, shift: str, db: Session = Depends(get_db)):
    from datetime import date
    try: day = date.fromisoformat(operating_date)
    except ValueError: raise HTTPException(422, "operating_date must be YYYY-MM-DD")
    sh = _shift(shift); _require_shift(db, sh)
    people_present = db.scalar(select(func.count()).select_from(PersonAttendance).where(
        PersonAttendance.operating_date == day, PersonAttendance.shift == sh,
        PersonAttendance.status == "PRESENT")) or 0
    equipment_present = db.scalar(select(func.count()).select_from(EquipmentAttendance).where(
        EquipmentAttendance.operating_date == day, EquipmentAttendance.shift == sh,
        EquipmentAttendance.status == "PRESENT")) or 0
    breakdown = db.scalar(select(func.count()).select_from(EquipmentAttendance).where(
        EquipmentAttendance.operating_date == day, EquipmentAttendance.shift == sh,
        EquipmentAttendance.condition == "BREAKDOWN")) or 0
    active_crew = db.scalar(select(func.count()).select_from(ShiftCrew).where(
        ShiftCrew.operating_date == day, ShiftCrew.shift == sh, ShiftCrew.status == "ACTIVE")) or 0
    active_deployment = db.scalar(select(func.count()).select_from(ShiftDeployment).where(
        ShiftDeployment.operating_date == day, ShiftDeployment.shift == sh, ShiftDeployment.status == "ACTIVE")) or 0
    state = "CLOSED" if _shift_is_closed(db, day, sh) else "OPEN"
    return {
        "operating_date": day, "shift": sh, "state": state,
        "people_present": people_present, "equipment_present": equipment_present,
        "equipment_breakdown": breakdown, "active_crew": active_crew,
        "active_deployment": active_deployment,
    }
