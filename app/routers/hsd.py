from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import HsdPurchaseLot, HsdIssue
from app.schemas import HsdReceiptIn, HsdIssueIn
from app.services.hsd_fifo import apply_fifo_issue
from app.services.time_context import operating_context

router = APIRouter(prefix="/api/hsd", tags=["hsd"])

@router.get("/tanker/{tanker_id}/stock")
def tanker_stock(tanker_id: str, db: Session = Depends(get_db)):
    stock = db.execute(select(func.coalesce(func.sum(HsdPurchaseLot.litres_remaining),0)).where(HsdPurchaseLot.tanker_id==tanker_id)).scalar_one()
    return {"tanker_id": tanker_id, "stock_l": stock}

@router.post("/receipt")
def receipt(p: HsdReceiptIn, db: Session = Depends(get_db)):
    old = db.execute(select(HsdPurchaseLot).where(HsdPurchaseLot.request_id==p.request_id)).scalar_one_or_none()
    if old: return {"ok": True, "lot_id": old.lot_id, "idempotent": True}
    _,_,now=operating_context(); amount=(p.litres*p.rate_per_l).quantize(Decimal("0.01"))
    lot=HsdPurchaseLot(lot_id=str(uuid4()), tanker_id=p.tanker_id, received_at=now,
        supplier=p.supplier, invoice_no=p.invoice_no, pump_location=p.pump_location,
        litres_received=p.litres, litres_remaining=p.litres, rate_per_l=p.rate_per_l,
        amount=amount, request_id=p.request_id)
    db.add(lot); db.commit(); return {"ok": True, "lot_id": lot.lot_id, "amount": amount}

@router.post("/issue")
def issue(p: HsdIssueIn, db: Session = Depends(get_db)):
    old = db.execute(select(HsdIssue).where(HsdIssue.request_id==p.request_id)).scalar_one_or_none()
    if old: return {"ok": True, "issue_id": old.issue_id, "amount": old.amount, "idempotent": True}
    day,shift,now=operating_context(); row=HsdIssue(issue_id=str(uuid4()), operating_date=day, shift=shift,
        tanker_id=p.tanker_id,machine_id=p.machine_id,litres=p.litres,amount=Decimal("0"),location_id=p.location_id,
        meter_type=p.meter_type,meter_reading=p.meter_reading,recipient_employee_id=p.recipient_employee_id,
        reference=p.reference,issued_at=now,request_id=p.request_id)
    try:
        allocations,total=apply_fifo_issue(db,row); db.commit()
    except ValueError as e:
        db.rollback(); raise HTTPException(409,str(e))
    return {"ok":True,"issue_id":row.issue_id,"amount":total,"allocations":[{"lot_id":a[0].lot_id,"litres":a[1],"rate":a[0].rate_per_l,"amount":a[2]} for a in allocations]}
