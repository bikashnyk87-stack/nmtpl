from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.reconcile import auto_reconcile

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])

@router.post("/run")
def run(operating_date: date, shift: str, db: Session = Depends(get_db)):
    result = auto_reconcile(db, operating_date, shift.upper())
    db.commit()
    return {"ok": True, **result}
