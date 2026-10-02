from __future__ import annotations
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import HsdPurchaseLot, HsdIssue, HsdIssueAllocation

def consume_fifo(db: Session, tanker_id: str, litres: Decimal):
    lots = db.execute(
        select(HsdPurchaseLot)
        .where(HsdPurchaseLot.tanker_id == tanker_id, HsdPurchaseLot.litres_remaining > 0)
        .order_by(HsdPurchaseLot.received_at.asc(), HsdPurchaseLot.lot_id.asc())
        .with_for_update()
    ).scalars().all()
    need = Decimal(litres)
    allocations = []
    total = Decimal("0")
    for lot in lots:
        if need <= 0:
            break
        take = min(need, lot.litres_remaining)
        amount = (take * lot.rate_per_l).quantize(Decimal("0.01"))
        allocations.append((lot, take, amount))
        total += amount
        need -= take
    if need > 0:
        raise ValueError(f"Insufficient tanker stock. Short by {need} L")
    return allocations, total

def apply_fifo_issue(db: Session, issue: HsdIssue):
    allocations, total = consume_fifo(db, issue.tanker_id, issue.litres)
    issue.amount = total
    db.add(issue)
    db.flush()
    for lot, litres, amount in allocations:
        lot.litres_remaining -= litres
        db.add(HsdIssueAllocation(
            issue_id=issue.issue_id,
            lot_id=lot.lot_id,
            litres=litres,
            rate_per_l=lot.rate_per_l,
            amount=amount,
        ))
    return allocations, total
