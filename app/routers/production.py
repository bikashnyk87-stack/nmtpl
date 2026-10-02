from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import uuid4
from app.db import get_db
from app.models import LoadTrip, ShiftState
from app.schemas import TripStartIn
from app.services.time_context import operating_context

router = APIRouter(prefix="/api/production", tags=["production"])

@router.post("/start")
def start_trip(p: TripStartIn, db: Session = Depends(get_db)):
    existing = db.execute(select(LoadTrip).where(LoadTrip.request_id == p.request_id)).scalar_one_or_none()
    if existing: return {"ok": True, "trip_id": existing.trip_id, "status": existing.status, "idempotent": True}
    day, shift, now = operating_context()
    state = db.execute(select(ShiftState).where(
        ShiftState.operating_date == day, ShiftState.shift == shift
    )).scalar_one_or_none()
    if state and state.status == "CLOSED":
        raise HTTPException(409, f"Shift {day} {shift} is CLOSED")
    if p.vehicle_id:
        busy = db.execute(select(LoadTrip).where(LoadTrip.vehicle_id==p.vehicle_id, LoadTrip.status.in_(["LOADING","HAULING"]))).scalar_one_or_none()
        if busy: raise HTTPException(409, f"{p.vehicle_id} is already {busy.status}")
    trip = LoadTrip(
        trip_id=str(uuid4()), operating_date=day, shift=shift,
        source_location_id=p.source_location_id, destination_location_id=p.destination_location_id,
        activity=p.activity.upper(), machine_id=p.machine_id, vehicle_id=p.vehicle_id,
        material_id=p.material_id, loading_start_at=now, status="LOADING",
        request_id=p.request_id, created_by=p.actor, created_at=now, updated_at=now,
    )
    db.add(trip); db.commit(); return {"ok": True, "trip_id": trip.trip_id, "status": trip.status}

@router.post("/{trip_id}/loaded")
def loaded(trip_id: str, db: Session = Depends(get_db)):
    trip = db.get(LoadTrip, trip_id)
    if not trip: raise HTTPException(404, "Trip not found")
    _,_,now=operating_context()
    if trip.status == "LOADING":
        trip.loading_end_at=now; trip.status="HAULING" if trip.vehicle_id else "CLOSED"; trip.updated_at=now; db.commit()
    return {"ok": True, "status": trip.status}

@router.post("/{trip_id}/unloaded")
def unloaded(trip_id: str, db: Session = Depends(get_db)):
    trip = db.get(LoadTrip, trip_id)
    if not trip: raise HTTPException(404, "Trip not found")
    if trip.status != "HAULING": raise HTTPException(409, "Trip is not in HAULING state")
    _,_,now=operating_context(); trip.unload_at=now; trip.status="CLOSED"; trip.updated_at=now; db.commit()
    return {"ok": True, "status": trip.status}
