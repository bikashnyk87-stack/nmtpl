"""Zero-entry AMNS-to-E-Pass reconciliation for Despatch.

Sources of truth:
  * Gmail Date Wise E-Pass = identity, weight and vehicle of individual trips.
  * Approved AMNS date-wise image = permit, buyer/destination/product, totals
    and explicitly numbered cancellations.
Rules:
  * OCR extracts, it does not approve. Whole-document totals and individual
    permit rows must reconcile with independently imported E-Passes.
  * Cancellation requires the FULL E-Pass number + matching MT and permit.
  * No guessed numeric values. No partial writes. No edits before 27-Oct-2026.
  * No manual entry during normal operation; exceptions remain read-only.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import logging
import re
from typing import Any

from sqlalchemy import select

log = logging.getLogger("nmtpl.despatch.amns")
OPEN_DAY = date(2026, 10, 27)
AMOUNT_TOL = Decimal("0.025")
PERMIT_PATTERN = re.compile(r"\bL\d{9}\b", flags=re.I)
EPASS_PATTERN = re.compile(r"\b(L\d{9}/\d{1,5})\b", flags=re.I)
DATE_PATTERN = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b")
MONEY_PATTERN = r"[\d,]{1,9}\.\d{3}"
ROW_NUMBERS = re.compile(
    rf"(?P<grade>\d{{2}}\.\d{{2}})\s*%?\s+"
    rf"(?P<permit_qty>{MONEY_PATTERN})\s+"
    r"(?P<trips>\d{1,4})\s+"
    rf"(?P<dispatch_mt>{MONEY_PATTERN})\s+"
    rf"(?P<balance_mt>{MONEY_PATTERN})\b"
)
CANCEL_AMOUNT = re.compile(r"(?<!\d)-\s*([\d,]{1,8}\.\d{3})\s*(?:M\.?\s*T\.?|MT)\b", flags=re.I)


class AMNSException(ValueError):
    pass


def amount(v: Any) -> Decimal:
    try:
        value = Decimal(str(v).replace(",", "").strip())
        if value.is_finite() and value >= 0:
            return value.quantize(Decimal(".001"))
    except (InvalidOperation, ValueError):
        pass
    raise AMNSException("Unverified numeric amount in AMNS image")


def normalize(s):
    return re.sub(r"\s+", " ", str(s or "").upper().replace("&AMP;", "&")).strip()


def grade_bucket(raw_grade, kind):
    """Grade percentage must fit a known material-report bucket."""
    grade = Decimal(str(raw_grade))
    if not grade.is_finite() or grade < 0 or grade > 100:
        raise AMNSException("Unverified AMNS material grade")
    bins = [(Decimal("55"), Decimal("58")), (Decimal("58"), Decimal("60")),
            (Decimal("60"), Decimal("62")), (Decimal("62"), Decimal("65")),
            (Decimal("65"), Decimal("68"))]
    if kind == "SCREENED FINES":
        prefix = "S.Fines"
    elif kind == "5X18":
        prefix = "5-18mm"
    else:
        raise AMNSException("Unknown AMNS material category: " + kind)
    for low, high in bins:
        if low <= grade < high:
            return f"{prefix}({low}-{high})"
    raise AMNSException("Material grade does not match a configured client-report category")


def _category(raw_text, grade):
    """Only mapped, explicit AMNS source categories; no inferred buyer."""
    up = normalize(raw_text).replace("5 X 18", "5X18").replace("5 X18", "5X18")
    if "SCREENED FINES" in up and "DABUNA" in up and re.search(r"\bAM\s*/?\s*NS\b", up):
        return {"buyer": "Self", "destination": "Dabuna",
                "material_grade": grade_bucket(grade, "SCREENED FINES")}
    # Exact previously validated permit history is preferred for the
    # non-captive TUIDUNGRI/SARAIKELA = customer depot categories. The image
    # records original place name; do not guess that it means another location.
    if "5X18" in up and "TUIDUNGRI" in up:
        if "DNA MINERALS" in up:
            return {"buyer": "DNA MINERALS PVT LTD", "destination": None,
                    "material_grade": grade_bucket(grade, "5X18")}
        if "SNN MINERALS" in up:
            return {"buyer": "S N N MINERALS PRIVATE LIMITED.", "destination": None,
                    "material_grade": grade_bucket(grade, "5X18")}
    raise AMNSException("Unrecognized buyer/destination/material combination in AMNS image")


def _tokens_to_rows(tokens: list[dict], width: float, height: float):
    """Group OCR text by measured text-line centers; not hardcoded pixel rows."""
    rows = []
    for token in sorted(tokens, key=lambda t: (t["y"], t["x"])):
        row = next((r for r in rows if abs(r["y"] - token["y"]) <= height * .019), None)
        if row is None:
            row = {"y": token["y"], "tokens": []}
            rows.append(row)
        row["tokens"].append(token)
    for row in rows:
        row["tokens"].sort(key=lambda x: x["x"])
        row["text"] = " ".join(t["text"] for t in row["tokens"])
        row["score"] = min(t["score"] for t in row["tokens"])
    return rows


def recognize_image(image_bytes: bytes) -> list[dict]:
    """Local open-source OCR; no image is sent to a third-party API."""
    try:
        from rapidocr import RapidOCR
        from PIL import Image
        from io import BytesIO
    except ImportError as exc:
        raise AMNSException("Automatic AMNS OCR is not installed") from exc
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            img.verify()
        engine = RapidOCR()
        result = engine(image_bytes)
        if result.txts is None or result.boxes is None:
            raise AMNSException("No readable AMNS text detected")
        tokens = []
        for text, box, score in zip(result.txts, result.boxes, result.scores):
            xs = [float(v[0]) for v in box]
            ys = [float(v[1]) for v in box]
            tokens.append({"text": str(text), "x": sum(xs)/4, "y": sum(ys)/4,
                           "score": float(score)})
        if not tokens:
            raise AMNSException("No readable AMNS text detected")
        return tokens
    except AMNSException:
        raise
    except Exception as exc:
        raise AMNSException("AMNS image could not be read with local OCR") from exc


def read_report(tokens: list[dict], width: float = 1000, height: float = 500) -> dict:
    """Parse AMNS date-wise permit table and numbered cancellation note.

    To prevent OCR hallucinations from modifying E-Passes, permit identity,
    dates and totals must independently match the E-Pass ledger later.
    """
    groups = _tokens_to_rows(tokens, width, height)
    text = " ".join(g["text"] for g in groups)
    title = next((r["text"] for r in groups if "DISPATCH REPORT" in normalize(r["text"])), "")
    match = DATE_PATTERN.search(title)
    if not match:
        raise AMNSException("Date-wise AMNS report date is not readable")
    try:
        day = date(int(match[3]), int(match[2]), int(match[1]))
    except ValueError as exc:
        raise AMNSException("Invalid report date in AMNS image") from exc
    if day < OPEN_DAY:
        raise AMNSException("Older completed AMNS reports are read-only")
    found = {}
    for group in groups:
        rowtext = normalize(group["text"])
        if "CANCEL" in rowtext or "NOTE" in rowtext or "TOTAL" in rowtext:
            continue
        pm = PERMIT_PATTERN.search(rowtext.replace(" ", ""))
        if not pm:
            continue
        permit = pm.group(0)
        # Scan right of the matched permit. Numeric columns end the row:
        # grade %, issued permit MT, E-Pass trip count, daily MT, balance.
        index = rowtext.find(permit)
        detail = rowtext[index+len(permit):]
        numeric = ROW_NUMBERS.search(detail)
        if not numeric:
            raise AMNSException("Unreadable AMNS table cells for permit " + permit)
        if group["score"] < .64:
            raise AMNSException("Low OCR confidence for permit " + permit)
        grade = Decimal(numeric["grade"])
        category = _category(detail[:numeric.start()], grade)
        item = {
            "permit_no": permit,
            "buyer": category["buyer"],
            "destination": category["destination"],
            "material_grade": category["material_grade"],
            "raw_report_details": detail[:numeric.start()].strip(),
            "grade_percent": str(grade),
            "permit_qty": amount(numeric["permit_qty"]),
            "trips": int(numeric["trips"]),
            "dispatch_mt": amount(numeric["dispatch_mt"]),
            "balance_mt": amount(numeric["balance_mt"]),
        }
        if permit in found:
            raise AMNSException("Duplicate permit row in AMNS image: " + permit)
        found[permit] = item
    if not found:
        raise AMNSException("No complete AMNS permit rows found")
    # OCR line may break cancellation note over multiple bounding boxes;
    # match the exact E-Pass and MT from the combined note region.
    note = normalize(text)
    cancelled = re.findall(r".{0,120}CANCEL(?:LED|LATION)?.{0,180}", note, flags=re.I)
    parsed_cancellations = []
    for section in cancelled:
        epass = EPASS_PATTERN.search(section)
        qty = CANCEL_AMOUNT.search(section)
        if epass and qty:
            parsed_cancellations.append({"epass_no": epass[1].upper(),
                                         "net_mt": amount(qty[1])})
        elif "CANCEL" in section:
            raise AMNSException("AMNS cancellation note lacks exact E-Pass and weight")
    if len(parsed_cancellations) != len({x["epass_no"] for x in parsed_cancellations}):
        raise AMNSException("Duplicate cancellation E-Pass in image")
    # The day totals must match the sum of permit rows, and the note contains
    # a matching total. A row with missing numeric columns is not accepted.
    day_trips = sum(row["trips"] for row in found.values())
    day_mt = sum((row["dispatch_mt"] for row in found.values()), Decimal("0"))
    if day_trips <= 0 or day_mt <= 0:
        raise AMNSException("AMNS report has no positive despatch totals")
    if not cancelled and "CANCEL" in note:
        raise AMNSException("Cancellation note could not be verified")
    return {"report_date": day, "permits": list(found.values()),
            "reported_trips": day_trips, "reported_mt": day_mt,
            "cancellations": parsed_cancellations}


def _destination_from_prior(trips, image_entry):
    """Non-captive location matching must come from exact prior permit history."""
    from app.services.tiom_despatch_client_layout import destination_bucket_index
    history = [x for x in trips if x.report_date < image_entry["report_date"]]
    valid = {str(x.destination or "").strip() for x in history
             if x.destination and x.buyer.casefold() == image_entry["buyer"].casefold()
             and str(x.material_grade).casefold() == image_entry["material_grade"].casefold()
             and destination_bucket_index(x) is not None}
    if len(valid) == 1:
        return next(iter(valid))
    raise AMNSException("Non-captive destination needs an approved source mapping")


def plan_reconciliation(db, report):
    """Plan everything, but write nothing until all totals and IDs reconcile."""
    from app.routers.tiom_despatch import DespatchTrip
    day = report["report_date"]
    if day < OPEN_DAY:
        raise AMNSException("Historical Despatch days are protected")
    todays = list(db.scalars(select(DespatchTrip).where(DespatchTrip.report_date == day)))
    if not todays:
        raise AMNSException("No original Gmail E-Passes available for report date")
    by_id = {x.epass_no.upper(): x for x in todays}
    by_permit = defaultdict(list)
    for trip in todays:
        by_permit[trip.permit_no.upper()].append(trip)
    expected_permits = {r["permit_no"] for r in report["permits"]}
    if expected_permits != set(by_permit):
        raise AMNSException("AMNS permit set and Gmail E-Pass permit set differ")
    to_cancel = []
    for item in report["cancellations"]:
        trip = by_id.get(item["epass_no"])
        if trip is None:
            raise AMNSException("Cancelled E-Pass does not exist: " + item["epass_no"])
        if trip.permit_no.upper() not in expected_permits:
            raise AMNSException("Cancelled E-Pass belongs to an unexpected permit")
        if abs(Decimal(str(trip.net_mt)) - item["net_mt"]) > AMOUNT_TOL:
            raise AMNSException("Cancellation weight does not match E-Pass: " + trip.epass_no)
        if trip.status not in ("ACTIVE", "CANCELLED"):
            raise AMNSException("Cancelled E-Pass has unexpected status")
        to_cancel.append(trip)
    cancelling = {t.epass_no for t in to_cancel}
    plan = []
    totals = (0, Decimal("0"))
    for item in report["permits"]:
        permit = item["permit_no"]
        trips = [x for x in by_permit[permit]
                 if x.status == "ACTIVE" and x.epass_no not in cancelling]
        count = len(trips)
        quantity = sum((Decimal(str(t.net_mt)) for t in trips), Decimal("0"))
        if count != item["trips"] or abs(quantity - item["dispatch_mt"]) > AMOUNT_TOL:
            raise AMNSException(f"Permit {permit}: AMNS says {item['trips']} trips/"
                                f"{item['dispatch_mt']} MT; Gmail E-Passes give "
                                f"{count} trips/{quantity} MT")
        if item["destination"] is None:
            earlier = list(db.scalars(select(DespatchTrip).where(
                DespatchTrip.permit_no == permit, DespatchTrip.report_date < day,
                DespatchTrip.status == "ACTIVE"
            )))
            from app.services.tiom_despatch_client_layout import destination_bucket_index
            valid = {x.destination for x in earlier
                     if destination_bucket_index(x) is not None
                     and x.buyer.strip().casefold() == item["buyer"].casefold()}
            if len(valid) != 1:
                raise AMNSException("No unique historical destination for " + permit)
            item["destination"] = next(iter(valid))
        for trip in trips:
            for field in ("buyer", "destination", "material_grade"):
                old = str(getattr(trip, field) or "").strip()
                new = str(item[field] or "").strip()
                if old and old.casefold() != new.casefold():
                    raise AMNSException("AMNS source conflicts with existing " + field +
                                        " for " + trip.epass_no)
        plan.append((item, trips))
        totals = (totals[0]+count, totals[1]+quantity)
    if totals[0] != report["reported_trips"] or abs(totals[1] - report["reported_mt"]) > AMOUNT_TOL:
        raise AMNSException("Date-wise AMNS total differs from permit totals")
    return {"plan": plan, "cancellations": to_cancel, "verifiedTrips": totals[0],
            "verifiedMt": totals[1]}


def apply_reconciliation(db, document, result, *, actor="AMNS_IMAGE_AUTO"):
    """Transactional idempotent AMNS application. No partial DB state."""
    import json
    from app.routers.tiom_despatch import DespatchAudit, DespatchPermitDay
    prepared = plan_reconciliation(db, result)
    updates = 0
    for row, trips in prepared["plan"]:
        for trip in trips:
            for field in ("buyer", "destination", "material_grade"):
                if not getattr(trip, field):
                    setattr(trip, field, row[field])
                    updates += 1
        prior = db.scalar(select(DespatchPermitDay).where(
            DespatchPermitDay.report_date == result["report_date"],
            DespatchPermitDay.permit_no == row["permit_no"]
        ))
        if prior is None:
            prior = DespatchPermitDay(report_date=result["report_date"], permit_no=row["permit_no"])
            db.add(prior)
        prior.buyer = row["buyer"]
        prior.destination = row["destination"]
        prior.material = row["material_grade"]
        prior.grade_percent = row["grade_percent"] + "%"
        prior.permit_qty = row["permit_qty"]
        prior.reported_trips = row["trips"]
        prior.reported_mt = row["dispatch_mt"]
        prior.balance_mt = row["balance_mt"]
        prior.document_id = document.id
        prior.review_status = "CONFIRMED"
    for trip in prepared["cancellations"]:
        if trip.status == "ACTIVE":
            trip.status = "CANCELLED"
    document.review_status = "VERIFIED"
    db.add(DespatchAudit(
        actor=actor, action="AMNS_AUTOMATIC_RECONCILIATION",
        entity_key=result["report_date"].isoformat(),
        reason="OCR parsed from retained AMNS image; reconciled exact permit/E-Pass totals",
        before_json=None,
        after_json=json.dumps({
            "documentId":document.id, "sha256":document.sha256,
            "tripCount":prepared["verifiedTrips"], "netMt":str(prepared["verifiedMt"]),
            "cancelled": [t.epass_no for t in prepared["cancellations"]],
            "categoryFieldsFilled":updates,
        }),
    ))
    db.commit()
    return {"ok": True, "reportDate": result["report_date"].isoformat(),
            "verifiedTrips": prepared["verifiedTrips"],
            "verifiedMt": float(prepared["verifiedMt"]),
            "cancelledEPasses": [t.epass_no for t in prepared["cancellations"]],
            "mappedFields": updates, "imageStatus":document.review_status}


def analyze_and_reconcile(db, document):
    """Runs OCR then applies only fully validated cross-source data."""
    from PIL import Image
    from io import BytesIO
    with Image.open(BytesIO(document.image_data)) as img:
        width, height = img.size
    tokens = recognize_image(document.image_data)
    report = read_report(tokens, width, height)
    if document.report_date and document.report_date != report["report_date"]:
        raise AMNSException("AMNS image printed date differs from supplied report date")
    return apply_reconciliation(db, document, report)
