from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import WbMovement, LoadTrip, LoadWbMatch, HsdIssue

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/shift")
def shift_summary(operating_date: date, shift: str, db: Session = Depends(get_db)):
    shift=shift.upper()
    wb = db.execute(select(func.count(), func.coalesce(func.sum(WbMovement.net_kg),0)).where(
        WbMovement.operating_date==operating_date,WbMovement.shift==shift,WbMovement.row_status=="VALID"
    )).one()
    matched = db.execute(select(func.count()).select_from(LoadWbMatch).join(LoadTrip, LoadTrip.trip_id==LoadWbMatch.trip_id).where(
        LoadTrip.operating_date==operating_date, LoadTrip.shift==shift, LoadWbMatch.status.in_(["MATCHED","LIKELY_MATCH"])
    )).scalar_one()
    hsd = db.execute(select(func.coalesce(func.sum(HsdIssue.litres),0),func.coalesce(func.sum(HsdIssue.amount),0)).where(
        HsdIssue.operating_date==operating_date,HsdIssue.shift==shift
    )).one()
    return {"date":operating_date,"shift":shift,"wb_trips":wb[0],"wb_tonnes":float(wb[1])/1000,
            "matched":matched,"hsd_litres":hsd[0],"hsd_cost":hsd[1]}
