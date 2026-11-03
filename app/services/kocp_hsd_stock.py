"""KOCP diesel stock ledger checks; no destructive changes to legacy transactions.

Daily closing balances use the actual posted opening, receipts and issues.
No inferred opening, no unclassified adjustments, and never a negative stock
balance. All HSD writers use a per-site PostgreSQL transaction advisory lock.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.site_models import SiteHsdTransaction

ZERO = Decimal("0")
KINDS = {"OPENING", "RECEIPT", "ISSUE", "ADJUSTMENT"}


def lock_hsd_ledger(db: Session, site_id: str) -> None:
    """Serialize stock-sensitive writers; SQL transactions release this lock."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"KOCP_HSD_LEDGER_{site_id}"},
        )


def evaluate_hsd_stock(
    db: Session, site_id: str, *,
    as_of: date | None = None,
    exclude_transaction_id: str | None = None,
    additional: tuple[date, str, Decimal] | None = None,
) -> dict:
    """Recompute one site ledger, optionally simulating a correction.

    All operations use posted rows only. Same-day movements are aggregated:
    individual dispensing order within a day cannot be inferred from missing
    source timestamps; this is explicitly a *daily* ledger guard.
    """
    stmt = select(
        SiteHsdTransaction.operating_date,
        SiteHsdTransaction.transaction_type,
        func.count(),
        func.coalesce(func.sum(SiteHsdTransaction.litres), 0),
    ).where(
        SiteHsdTransaction.site_id == site_id,
        SiteHsdTransaction.status == "POSTED",
    )
    if exclude_transaction_id:
        stmt = stmt.where(SiteHsdTransaction.transaction_id != exclude_transaction_id)
    stmt = stmt.group_by(
        SiteHsdTransaction.operating_date, SiteHsdTransaction.transaction_type
    )
    by_day: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    count_open = 0
    opening_date = None
    opening_litres = ZERO
    errors = []
    for day, kind, count, litres in db.execute(stmt):
        kind = str(kind or "").upper()
        amount = Decimal(str(litres))
        if kind == "OPENING":
            count_open += int(count)
            opening_date = day
            opening_litres += amount
        elif kind in {"RECEIPT", "ISSUE"}:
            by_day[day][kind] += amount
        elif kind == "ADJUSTMENT":
            errors.append("Unclassified adjustment exists; reconcile it before issuing fuel.")
        else:
            errors.append(f"Unrecognized HSD transaction type {kind}.")
    if additional:
        day, kind, amount = additional
        kind = str(kind).upper()
        amount = Decimal(str(amount))
        if kind == "OPENING":
            count_open += 1
            opening_date = day
            opening_litres += amount
        elif kind in {"RECEIPT", "ISSUE"}:
            by_day[day][kind] += amount
        else:
            errors.append("Unsupported fuel adjustment type.")
    if count_open == 0:
        errors.append("Opening stock is not verified. Ask the administrator to enter the actual opening balance.")
    elif count_open != 1:
        errors.append("Multiple posted openings found; stock requires reconciliation.")
    if count_open == 1 and opening_litres < 0:
        errors.append("Opening stock cannot be negative.")
    running = opening_litres
    stock_by_day = {}
    if count_open == 1 and opening_date:
        for day in sorted(by_day):
            if day < opening_date:
                errors.append("Fuel movements predate the verified opening stock.")
            running += by_day[day]["RECEIPT"] - by_day[day]["ISSUE"]
            stock_by_day[day] = running
            if running < ZERO:
                errors.append(f"Insufficient verified fuel: daily ledger becomes negative on {day.isoformat()}.")
        if as_of is not None:
            balance = opening_litres if as_of >= opening_date else None
            if balance is not None:
                for day in sorted(stock_by_day):
                    if day <= as_of:
                        balance = stock_by_day[day]
        else:
            balance = running
    else:
        balance = None
    verified = not errors
    return {
        "verified": verified, "balance": balance if verified else None,
        "openingDate": opening_date, "openingLitres": opening_litres if count_open == 1 else None,
        "openingCount": count_open,
        "reason": errors[0] if errors else None,
        "issues": errors,
        "lastBalance": running if count_open == 1 else None,
    }


def require_fuel_available(db: Session, site_id: str, day: date, litres: Decimal) -> Decimal:
    """Validate before posting *every* new KOCP HSD issue."""
    prior = evaluate_hsd_stock(db, site_id, as_of=day)
    if not prior["verified"]:
        raise HTTPException(409, prior["reason"])
    available = prior["balance"]
    amount = Decimal(str(litres))
    if available is None or available < amount:
        raise HTTPException(
            409, f"Insufficient HSD stock: available {available or ZERO:.3f} L, requested {amount:.3f} L."
        )
    after = evaluate_hsd_stock(db, site_id, additional=(day, "ISSUE", amount))
    if not after["verified"]:
        raise HTTPException(409, after["reason"])
    return available - amount
