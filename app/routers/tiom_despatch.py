"""TIOM despatch ledger. Separate from internal WB and production movements."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parseaddr
from io import BytesIO, StringIO
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Date, DateTime, Integer, LargeBinary, Numeric, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.auth import csrf, get_user, require
from app.db import Base, get_db

router = APIRouter(prefix="/api/tiom/despatch", tags=["TIOM Despatch"])

DEFAULT_SENDERS = (
    ("sanjaymahakud50@gmail.com", "Sanjay Mahakud"),
    ("dillip.sahu80@gmail.com", "Dillip Kumar Sahu"),
    ("chinmaykumarpanda@gmail.com", "Chinmay Panda"),
    ("binodsingh8018@gmail.com", "Binod Singh"),
    ("tarunnayak63@gmail.com", "Tarun Kumar Nayak"),
    ("sanjaykumarbarik1982@gmail.com", "Sanjay Kumar Barik"),
    ("niranjanbabu95@gmail.com", "Niranjan Mahanta"),
    ("rajugupta97093@gmail.com", "Bansilal Gupta"),
    ("sumantakumarmahanta@gmail.com", "Sumanta Kumar Mahanta"),
)


class DespatchSender(Base):
    __tablename__ = "tiom_despatch_sender"
    email: Mapped[str] = mapped_column(String(200), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DespatchTrip(Base):
    __tablename__ = "tiom_despatch_trip"
    epass_no: Mapped[str] = mapped_column(String(120), primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    permit_no: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    permit_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    buyer: Mapped[str] = mapped_column(String(240), default="")
    vehicle_no: Mapped[str] = mapped_column(String(80), default="")
    transporter: Mapped[str] = mapped_column(String(240), default="")
    destination: Mapped[str] = mapped_column(String(240), default="")
    material_grade: Mapped[str] = mapped_column(String(160), default="")
    stack_no: Mapped[str] = mapped_column(String(100), default="")
    consignee: Mapped[str] = mapped_column(String(300), default="")
    tare_mt: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    gross_mt: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    net_mt: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    dispatch_time: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(200), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DespatchDocument(Base):
    __tablename__ = "tiom_despatch_document"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    report_date: Mapped[date | None] = mapped_column(Date, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), default="NEEDS_REVIEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DespatchPermitDay(Base):
    __tablename__ = "tiom_despatch_permit_day"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    permit_no: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    buyer: Mapped[str] = mapped_column(String(200), default="")
    destination: Mapped[str] = mapped_column(String(200), default="")
    material: Mapped[str] = mapped_column(String(120), default="")
    grade_percent: Mapped[str] = mapped_column(String(40), default="")
    permit_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    reported_trips: Mapped[int | None] = mapped_column(Integer)
    reported_mt: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    balance_mt: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    document_id: Mapped[str | None] = mapped_column(String(40))
    review_status: Mapped[str] = mapped_column(String(30), default="NEEDS_REVIEW")


class DespatchAudit(Base):
    __tablename__ = "tiom_despatch_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(40))
    entity_key: Mapped[str] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(Text, default="")
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)


def _user(request, db, edit=False):
    user = get_user(db, request)
    require(user, "PRODUCTION")
    if edit and not user.admin:
        raise HTTPException(403, "Despatch corrections and sender changes require management.")
    return user


def _seed_senders(db):
    existing = set(db.scalars(select(DespatchSender.email)).all())
    if not existing:
        db.add_all(DespatchSender(email=e, name=n, active=True) for e, n in DEFAULT_SENDERS)
        db.commit()


def _amount(value):
    try:
        out = Decimal(str(value if value is not None and value != "" else 0))
        if not out.is_finite():
            raise InvalidOperation()
        return out.quantize(Decimal("0.001"))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid dispatch quantity or weight")


def _date(value, fallback=None):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for pattern in ("%Y-%m-%d", "%d.%m.%y", "%d/%m/%Y", "%b %d %Y", "%b  %d %Y"):
        try:
            return datetime.strptime(str(value or "").strip(), pattern).date()
        except ValueError:
            pass
    if fallback:
        return fallback
    raise ValueError("Invalid dispatch date")


def _trip(d):
    def item(name):
        return str(d.get(name) or "").strip()
    epass = item("epass_no")
    if not epass or len(epass) > 120:
        raise ValueError("Missing or invalid E-Pass No.")
    day = _date(item("report_date"))
    if day < date(2026, 10, 1):
        raise ValueError("Despatch backfill starts from 2026-10-01")
    tare, gross, net = (_amount(item(k)) for k in ("tare_mt", "gross_mt", "net_mt"))
    if min(tare, gross, net) < 0 or abs((gross - tare) - net) > Decimal(".025"):
        raise ValueError("Gross - tare does not match net weight")
    return dict(
        epass_no=epass, report_date=day, permit_no=item("permit_no"),
        permit_qty=_amount(item("permit_qty")), buyer=item("buyer"),
        vehicle_no=item("vehicle_no"), transporter=item("transporter"),
        destination=item("destination"), material_grade=item("material_grade"),
        stack_no=item("stack_no"), consignee=item("consignee"),
        tare_mt=tare, gross_mt=gross, net_mt=net, dispatch_time=item("dispatch_time"),
        status="ACTIVE", source=item("source")[:200],
    )


def _extract(data, filename):
    if filename.lower().endswith(".csv"):
        text = data.decode("utf-8-sig")
        if not text.startswith("report_date,") and "report_date" not in text.splitlines()[0]:
            raise ValueError("CSV must use TIOM October import column headings")
        return list(csv.DictReader(StringIO(text)))
    if not filename.lower().endswith(".xlsx"):
        raise ValueError("Use Trip Summary XLSX or TIOM dispatch CSV")
    wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    extracted = []
    try:
        for ws in wb:
            try:
                day = datetime.strptime(ws.title, "%d.%m.%y").date()
            except ValueError:
                continue  # Never import cumulative sheet a second time.
            header = [str(x.value or "").strip().casefold() for x in next(ws.iter_rows(min_row=2, max_row=2))]
            if not all(x in header for x in ("e-pass no", "net wt.", "permit no.")):
                continue
            for row in ws.iter_rows(min_row=3, values_only=True):
                if len(row) < 16 or not str(row[4] or "").strip():
                    continue
                extracted.append(dict(zip(
                    ("serial", "permit_no", "permit_qty", "buyer", "epass_no",
                     "vehicle_no", "transporter", "destination", "material_grade",
                     "stack_no", "consignee", "tare_mt", "gross_mt", "net_mt",
                     "dispatch_date", "dispatch_time"), row[:16]
                ), report_date=day.isoformat(), source=filename + " / " + ws.title))
    finally:
        wb.close()
    if not extracted:
        raise ValueError("No dated Trip Summary sheets with E-Pass rows found")
    return extracted


def _import_data(db, data, filename, actor):
    if len(data) > 12_000_000:
        raise ValueError("File exceeds 12 MB")
    raw = _extract(data, filename)
    if len(raw) > 100_000:
        raise ValueError("Too many rows")
    seen = set()
    trip_records = []
    errors = []
    for i, row in enumerate(raw, 1):
        try:
            trip = _trip(row)
            key = trip["epass_no"].upper()
            if key in seen:
                raise ValueError("Repeated E-Pass within the upload")
            seen.add(key)
            trip_records.append(trip)
        except ValueError as exc:
            errors.append({"row": i, "error": str(exc)})
    if errors:
        return {"ok": False, "inserted": 0, "errors": errors[:30], "errorCount": len(errors), "reviewRequired": True}
    # Batch lookups: the PC SQLite mirror may have a 999-bind limit.
    existing = {}
    keys = [x["epass_no"] for x in trip_records]
    for offset in range(0, len(keys), 500):
        for trip in db.scalars(select(DespatchTrip).where(
            DespatchTrip.epass_no.in_(keys[offset:offset + 500])
        )):
            existing[trip.epass_no.upper()] = trip
    inserted = 0
    mismatches = []
    for entry in trip_records:
        old = existing.get(entry["epass_no"].upper())
        if old:
            if old.net_mt != entry["net_mt"] or old.report_date != entry["report_date"]:
                mismatches.append(entry["epass_no"])
            continue
        db.add(DespatchTrip(**entry))
        inserted += 1
    db.add(DespatchAudit(actor=actor, action="IMPORT", entity_key=filename[:160],
                         reason="Historical despatch data import",
                         before_json=None,
                         after_json=json.dumps({"inserted": inserted, "duplicates": len(raw)-inserted,
                                                "conflicts": mismatches[:100]})))
    db.commit()
    return {"ok": True, "inserted": inserted, "skippedExisting": len(raw)-inserted,
            "conflicts": mismatches[:30], "conflictCount": len(mismatches)}


def _as_dict(x):
    return {c.name: (str(getattr(x, c.name)) if isinstance(getattr(x, c.name), (Decimal, date, datetime)) else getattr(x, c.name))
            for c in x.__table__.columns if c.name not in {"image_data"}}


@router.get("/senders")
def senders(request: Request, db: Session = Depends(get_db)):
    _user(request, db)
    _seed_senders(db)
    return [_as_dict(x) for x in db.scalars(select(DespatchSender).order_by(DespatchSender.email))]


class SenderIn(BaseModel):
    email: str = Field(min_length=6, max_length=200)
    name: str = Field(default="", max_length=160)
    active: bool = True


@router.post("/senders")
def set_sender(p: SenderIn, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    user = _user(request, db, edit=True)
    _seed_senders(db)
    email = p.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(422, "Invalid sender email address")
    old = db.get(DespatchSender, email)
    before = _as_dict(old) if old else None
    if old:
        old.name = p.name.strip() or old.name
        old.active = p.active
    else:
        old = DespatchSender(email=email, name=p.name.strip() or email, active=p.active)
        db.add(old)
    db.add(DespatchAudit(actor=user.login_id, action="SENDER_CONFIG", entity_key=email,
                         reason="Sender allowlist administration", before_json=json.dumps(before),
                         after_json=json.dumps({"active": p.active, "name": old.name})))
    db.commit()
    return _as_dict(old)


@router.post("/upload")
async def upload_trips(request: Request, file: UploadFile = File(...),
                       db: Session = Depends(get_db)):
    csrf(request)
    user = _user(request, db, edit=True)
    data = await file.read(12_000_001)
    try:
        return _import_data(db, data, file.filename or "upload.xlsx", user.login_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


class TripEdit(BaseModel):
    status: str | None = None
    net_mt: Decimal | None = None
    tare_mt: Decimal | None = None
    gross_mt: Decimal | None = None
    report_date: date | None = None
    permit_no: str | None = None
    buyer: str | None = None
    transporter: str | None = None
    destination: str | None = None
    material_grade: str | None = None
    vehicle_no: str | None = None
    reason: str = Field(min_length=5, max_length=500)


@router.post("/trip/{epass_no:path}/edit")
def edit_trip(epass_no: str, p: TripEdit, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    user = _user(request, db, edit=True)
    trip = db.get(DespatchTrip, epass_no)
    if not trip:
        raise HTTPException(404, "E-pass not found")
    before = _as_dict(trip)
    changes = p.model_dump(exclude_none=True, exclude={"reason"})
    if not changes:
        raise HTTPException(422, "No correction supplied")
    for key, value in changes.items():
        if key == "status" and value not in {"ACTIVE", "CANCELLED"}:
            raise HTTPException(422, "Status must be ACTIVE or CANCELLED")
        setattr(trip, key, value)
    if min(trip.tare_mt, trip.gross_mt, trip.net_mt) < 0 or abs(trip.gross_mt - trip.tare_mt - trip.net_mt) > Decimal(".025"):
        db.rollback()
        raise HTTPException(422, "Gross - tare must equal net")
    trip.updated_at = datetime.now(timezone.utc)
    db.add(DespatchAudit(actor=user.login_id, action="CORRECT_TRIP",
                         entity_key=epass_no, reason=p.reason.strip(), before_json=json.dumps(before),
                         after_json=json.dumps(_as_dict(trip))))
    db.commit()
    return {"ok": True, "trip": _as_dict(trip)}


@router.get("/trips")
def trips(request: Request, from_date: date = date(2026, 10, 1),
          to_date: date = date(2026, 10, 31), q: str = "", page: int = 1,
          show_cancelled: bool = False, db: Session = Depends(get_db)):
    _user(request, db)
    if (to_date - from_date).days > 370 or page < 1:
        raise HTTPException(422, "Invalid date range or page")
    query = select(DespatchTrip).where(DespatchTrip.report_date.between(from_date, to_date))
    if not show_cancelled:
        query = query.where(DespatchTrip.status == "ACTIVE")
    if q.strip():
        from sqlalchemy import or_
        term = "%" + q.strip()[:90] + "%"
        query = query.where(or_(DespatchTrip.epass_no.ilike(term),
                                DespatchTrip.vehicle_no.ilike(term),
                                DespatchTrip.permit_no.ilike(term),
                                DespatchTrip.transporter.ilike(term)))
    count = db.scalar(select(func.count()).select_from(query.subquery()))
    result = db.scalars(query.order_by(DespatchTrip.report_date.desc(), DespatchTrip.epass_no)
                        .limit(100).offset((page-1)*100)).all()
    return {"count": count, "page": page, "rows": [_as_dict(r) for r in result]}


@router.get("/dashboard")
def dashboard(request: Request, from_date: date = date(2026, 10, 1),
              to_date: date = date(2026, 10, 31), db: Session = Depends(get_db)):
    _user(request, db)
    if to_date < from_date or (to_date-from_date).days > 370:
        raise HTTPException(422, "Invalid period")
    base = (DespatchTrip.report_date.between(from_date, to_date))
    active = (base & (DespatchTrip.status == "ACTIVE"))
    totals = db.execute(select(func.count(), func.coalesce(func.sum(DespatchTrip.net_mt), 0))
                        .where(active)).one()
    def breakdown(col, top=None):
        stmt = (select(col.label("name"), func.count().label("trips"),
                       func.sum(DespatchTrip.net_mt).label("tonnes"))
                .where(active).group_by(col).order_by(func.sum(DespatchTrip.net_mt).desc()))
        if top:
            stmt = stmt.limit(top)
        return [{"name": k or "(blank)", "trips": int(t), "tonnes": float(mt)}
                for k, t, mt in db.execute(stmt)]
    daily = [{"date": d.isoformat(), "trips": int(t), "tonnes": float(mt)}
             for d, t, mt in db.execute(
                 select(DespatchTrip.report_date, func.count(), func.sum(DespatchTrip.net_mt))
                 .where(active).group_by(DespatchTrip.report_date).order_by(DespatchTrip.report_date)
             )]
    unreviewed = db.scalar(select(func.count()).select_from(DespatchDocument)
                            .where(DespatchDocument.review_status == "NEEDS_REVIEW"))
    cancelled = db.scalar(select(func.count()).select_from(DespatchTrip)
                          .where(base & (DespatchTrip.status == "CANCELLED")))
    return {"period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
            "totals": {"trips": int(totals[0]), "tonnes": float(totals[1]),
                       "cancelled": int(cancelled or 0), "imagesReview": int(unreviewed or 0)},
            "daily": daily, "destination": breakdown(DespatchTrip.destination, 15),
            "material": breakdown(DespatchTrip.material_grade, 15),
            "transporter": breakdown(DespatchTrip.transporter, 15),
            "buyer": breakdown(DespatchTrip.buyer, 15)}


@router.post("/image")
async def upload_image(request: Request, file: UploadFile = File(...),
                       report_date: date | None = Form(default=None),
                       db: Session = Depends(get_db)):
    csrf(request)
    user = _user(request, db, edit=True)
    contents = await file.read(8_000_001)
    ctype = (file.content_type or "").lower()
    if not (ctype in {"image/jpeg", "image/png", "image/webp"} and len(contents) <= 8_000_000):
        raise HTTPException(422, "Upload a JPEG, PNG or WEBP image up to 8 MB")
    digest = hashlib.sha256(contents).hexdigest()
    old = db.scalar(select(DespatchDocument).where(DespatchDocument.sha256 == digest))
    if old:
        return {"ok": True, "id": old.id, "duplicate": True}
    doc = DespatchDocument(id=uuid4().hex, report_date=report_date,
                           filename=(file.filename or "AMNS image")[:255],
                           media_type=ctype, sha256=digest, image_data=contents)
    db.add(doc)
    db.add(DespatchAudit(actor=user.login_id, action="IMAGE_UPLOAD", entity_key=doc.id,
                         reason="Image retained for comparison; needs manual review",
                         before_json=None, after_json=json.dumps({"filename": doc.filename, "date": str(report_date)})))
    db.commit()
    return {"ok": True, "id": doc.id, "reviewStatus": "NEEDS_REVIEW"}


@router.get("/images")
def images(request: Request, db: Session = Depends(get_db)):
    _user(request, db)
    rows = db.scalars(select(DespatchDocument).order_by(DespatchDocument.created_at.desc()).limit(100)).all()
    return [_as_dict(x) for x in rows]


@router.get("/image/{document_id}")
def image(document_id: str, request: Request, db: Session = Depends(get_db)):
    _user(request, db)
    row = db.get(DespatchDocument, document_id)
    if not row:
        raise HTTPException(404, "Image not found")
    return Response(row.image_data, media_type=row.media_type, headers={"Cache-Control": "private, no-store"})


class PermitReview(BaseModel):
    report_date: date
    permit_no: str
    buyer: str = ""
    destination: str = ""
    material: str = ""
    grade_percent: str = ""
    permit_qty: Decimal | None = None
    reported_trips: int | None = None
    reported_mt: Decimal | None = None
    balance_mt: Decimal | None = None
    document_id: str | None = None


@router.post("/permit-review")
def save_permit_review(p: PermitReview, request: Request, db: Session = Depends(get_db)):
    csrf(request)
    user = _user(request, db, edit=True)
    if not p.permit_no.strip():
        raise HTTPException(422, "Permit number required")
    if p.grade_percent and (not re.fullmatch(r"\d{1,2}(?:\.\d{1,3})?%?", p.grade_percent) or float(p.grade_percent.rstrip("%")) > 100):
        raise HTTPException(422, "Grade requires correction; cannot exceed 100%")
    if p.document_id and not db.get(DespatchDocument, p.document_id):
        raise HTTPException(422, "Image reference not found")
    old = db.scalar(select(DespatchPermitDay).where(
        DespatchPermitDay.report_date == p.report_date,
        DespatchPermitDay.permit_no == p.permit_no))
    before = _as_dict(old) if old else None
    if not old:
        old = DespatchPermitDay(report_date=p.report_date, permit_no=p.permit_no)
        db.add(old)
    for key, value in p.model_dump(exclude={"report_date", "permit_no"}).items():
        setattr(old, key, value)
    old.review_status = "CONFIRMED"
    db.add(DespatchAudit(actor=user.login_id, action="AMNS_PERMIT_REVIEW",
                         entity_key=p.permit_no, reason="Image verified entry",
                         before_json=json.dumps(before), after_json=p.model_dump_json()))
    db.commit()
    return {"ok": True, "permit": _as_dict(old)}


@router.get("/permit-reviews")
def permit_reviews(request: Request, from_date: date = date(2026, 10, 1),
                   to_date: date = date(2026, 10, 31), db: Session = Depends(get_db)):
    _user(request, db)
    rows = db.scalars(select(DespatchPermitDay)
                      .where(DespatchPermitDay.report_date.between(from_date, to_date))
                      .order_by(DespatchPermitDay.report_date.desc())).all()
    return [_as_dict(x) for x in rows]


@router.get("/export/{report_type}")
def export_report(report_type: str, request: Request, from_date: date = date(2026, 10, 1),
                  to_date: date = date(2026, 10, 31), db: Session = Depends(get_db)):
    _user(request, db)
    if report_type not in {"trip", "transporter", "material", "destination", "despatch"}:
        raise HTTPException(404, "Unknown report")
    if (to_date - from_date).days > 370 or to_date < from_date:
        raise HTTPException(422, "Invalid period")
    wb = Workbook()
    ws = wb.active
    names = {"trip": "TRIP SUMMARY", "transporter": "TRANSPORTER WISE DISPATCH",
             "material": "MATERIAL WISE DISPATCH", "destination": "DESTINATION WISE REPORT",
             "despatch": "DESPATCH REPORT"}
    ws.title = names[report_type][:31]
    ws.merge_cells("A1:P1" if report_type == "trip" else "A1:E1")
    ws["A1"] = f"TIOM — {names[report_type]} ({from_date:%d.%m.%Y} to {to_date:%d.%m.%Y})"
    ws["A1"].font = Font(bold=True, size=14)
    all_trips = db.scalars(select(DespatchTrip)
                           .where(DespatchTrip.report_date.between(from_date, to_date),
                                  DespatchTrip.status == "ACTIVE")
                           .order_by(DespatchTrip.report_date, DespatchTrip.epass_no)).all()
    if report_type == "trip":
        heads = ["Sl.No.", "Permit No.", "Permit Qty.", "Buyer Name", "E-Pass No",
                 "Vehicle RegNo", "Transporter Name", "Destination", "Material/Grade",
                 "Stack No.", "Consignee Name", "Tare Wt.", "Gross Wt.", "Net Wt.", "Date", "Time"]
        rows = [(i, x.permit_no, float(x.permit_qty), x.buyer, x.epass_no,
                 x.vehicle_no, x.transporter, x.destination, x.material_grade,
                 x.stack_no, x.consignee, float(x.tare_mt), float(x.gross_mt),
                 float(x.net_mt), x.report_date.isoformat(), x.dispatch_time)
                for i, x in enumerate(all_trips, 1)]
    else:
        from collections import defaultdict
        groups = defaultdict(lambda: [0, Decimal("0")])
        for x in all_trips:
            if report_type == "transporter":
                key = (x.transporter, x.destination, x.material_grade)
            elif report_type == "material":
                key = (x.report_date.isoformat(), x.material_grade)
            elif report_type == "destination":
                key = (x.buyer, x.destination, x.material_grade)
            else:
                key = (x.report_date.isoformat(),
                       "CAPTIVE" if (x.buyer.casefold() == "self" or "ARCELOR" in x.consignee.upper()) else "NON CAPTIVE",
                       x.destination)
            groups[key][0] += 1
            groups[key][1] += x.net_mt
        heads = {
            "transporter": ["Transporter", "Destination", "Material/Grade", "Trips", "Despatch MT"],
            "material": ["Date", "Material/Grade", "Trips", "Despatch MT"],
            "destination": ["Buyer Name", "Destination", "Material/Grade", "Trips", "Despatch MT"],
            "despatch": ["Date", "Captive / Non-captive", "Destination", "Trips", "Despatch MT"],
        }[report_type]
        rows = [(*key, count, float(mt)) for key, (count, mt) in sorted(groups.items())]
    for i, v in enumerate(heads, 1):
        c = ws.cell(3, i, v)
        c.fill = PatternFill("solid", fgColor="163D52")
        c.font = Font(color="FFFFFF", bold=True)
        c.alignment = Alignment(wrap_text=True)
    for i, row in enumerate(rows, 4):
        for col, v in enumerate(row, 1):
            ws.cell(i, col, v)
    for col in range(1, len(heads)+1):
        ws.column_dimensions[__import__("openpyxl").utils.get_column_letter(col)].width = (
            24 if col <= 4 else 18)
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:{__import__('openpyxl').utils.get_column_letter(len(heads))}{max(4, len(rows)+3)}"
    last = len(rows)+5
    ws.cell(last, 1, "TOTAL")
    if report_type == "trip":
        # Original Trip Summary totals are N1 (count) and P1 (net MT).
        # Never put totals into the Date and Time columns.
        ws["N1"] = len(all_trips)
        ws["P1"] = float(sum((x.net_mt for x in all_trips), Decimal(0)))
        ws.cell(last, 14, float(sum((x.net_mt for x in all_trips), Decimal(0))))
    else:
        ws.cell(last, len(heads)-1, len(all_trips))
        ws.cell(last, len(heads), float(sum((x.net_mt for x in all_trips), Decimal(0))))
    for c in ws[last]:
        c.font = Font(bold=True)
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="TIOM_{report_type}_{from_date}_{to_date}.xlsx"'})

@router.post("/mail-sync")
def mail_sync(request: Request, db: Session = Depends(get_db)):
    """Management-triggered mailbox sync, separate from WB ingestion."""
    csrf(request)
    _user(request, db, edit=True)
    from app.services.tiom_despatch_mail import gmail_scan
    try:
        return gmail_scan(50)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
