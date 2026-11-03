"""Only source-verified, permit-keyed categorization of imported Despatch E-Passes.

Completed historic 1–26 October 2026 E-Pass fields are a trustworthy permit
reference. Never infer a new permit's material/destination from weights,
consignee name or a nearby permit. Do not change numeric weights, trip counts,
cancelled rows, old period records, or existing nonempty source classifications.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
import json

from sqlalchemy import select

from app.services.tiom_despatch_client_layout import (
    DESTINATION_BUCKETS, MATERIAL_COLUMNS, destination_bucket_index,
    classified_material, normalized, reportable_category,
)

OPEN_DAY = date(2026, 10, 27)
CLOSED_DAY = date(2026, 10, 26)
FIELDS = ("buyer", "destination", "material_grade")
VALID_MATERIALS = {normalized(x) for x in MATERIAL_COLUMNS}


def _group_candidate(rows):
    """Use permit history only when every category has exactly one value."""
    if not rows:
        return None
    vals = {}
    for field in FIELDS:
        seen = {}
        for row in rows:
            value = str(getattr(row, field, "") or "").strip()
            if value:
                seen.setdefault(normalized(value), value)
        if len(seen) != 1:
            return None
        vals[field] = next(iter(seen.values()))
    # A permit may legitimately have a new beneficiary; require a consistent
    # nonempty consignee if the source provides one.
    consignees = {normalized(x.consignee) for x in rows
                  if getattr(x, "consignee", None)}
    if len(consignees) > 1:
        return None
    vals["consignee_key"] = next(iter(consignees), "")
    amounts = {Decimal(str(x.permit_qty)) for x in rows
               if getattr(x, "permit_qty", None) is not None
               and Decimal(str(x.permit_qty)) > 0}
    vals["permit_qty"] = next(iter(amounts)) if len(amounts) == 1 else None
    vals["historicalRows"] = len(rows)
    return vals


def _matches_existing(row, candidate):
    for field in FIELDS:
        current = str(getattr(row, field, "") or "").strip()
        if current and normalized(current) != normalized(candidate[field]):
            return False
    old_consignee = candidate.get("consignee_key")
    if old_consignee and row.consignee and normalized(row.consignee) != old_consignee:
        return False
    return True


def _is_classified(row):
    return reportable_category(row)


def mapping_status(db, day: date):
    from app.routers.tiom_despatch import DespatchTrip, DespatchDocument
    from app.services.tiom_despatch_client_layout import material_normalized
    if day < OPEN_DAY:
        return {"reportDate": day.isoformat(), "closed": True, "totalTrips": 0,
                "unmappedTrips": 0, "permits": [], "categories": [], "images": []}
    trips = list(db.scalars(select(DespatchTrip).where(
        DespatchTrip.report_date == day, DespatchTrip.status == "ACTIVE"
    )))
    pending = defaultdict(list)
    for x in trips:
        if not _is_classified(x):
            pending[x.permit_no].append(x)
    prior = list(db.scalars(select(DespatchTrip).where(
        DespatchTrip.report_date < day, DespatchTrip.status == "ACTIVE"
    )))
    by_permit = defaultdict(list)
    for x in prior:
        by_permit[x.permit_no].append(x)
    permits = []
    for permit, entries in pending.items():
        candidate = _group_candidate(by_permit.get(permit, []))
        compatible = bool(candidate and all(_matches_existing(x, candidate) for x in entries))
        earlier = [x for x in by_permit.get(permit, []) if
                   OPEN_DAY <= x.report_date < day and not _is_classified(x)]
        permits.append({
            "permit_no": permit,
            "tripCount": len(entries),
            "relatedUnclassifiedTrips": len(earlier) + len(entries),
            "relatedDates": sorted({x.report_date.isoformat() for x in earlier + entries}),
            "netMt": float(sum((Decimal(str(x.net_mt)) for x in entries), Decimal("0"))),
            "consignee": next((x.consignee for x in entries if x.consignee), ""),
            "sourceMapped": compatible,
            "candidate": {k: str(candidate[k]) for k in FIELDS} if compatible else None,
            "classification": "MATCHES_PREVIOUS_PERMIT" if compatible else "VERIFY_NEW_PERMIT",
        })
    # AMNS permit authorization can precede subsequent days' E-Pass dispatches.
    # Keep the original document date visible so operators must confirm the
    # exact permit, buyer, destination and grade before reusing evidence.
    images = list(db.scalars(select(DespatchDocument).where(
        DespatchDocument.report_date >= OPEN_DAY,
        DespatchDocument.report_date <= day,
    ).order_by(DespatchDocument.report_date.desc(),
               DespatchDocument.created_at.desc()).limit(150)))
    return {
        "reportDate": day.isoformat(), "closed": False, "totalTrips": len(trips),
        "unmappedTrips": sum(len(x) for x in pending.values()),
        "permits": sorted(permits, key=lambda x: (-x["tripCount"], x["permit_no"])),
        "categories": [{"index": i, "buyer": x[0], "destination": x[1], "material": x[2]}
                       for i, x in enumerate(DESTINATION_BUCKETS)
                       if material_normalized(x[2], day) in VALID_MATERIALS],
        "images": [{"id": i.id, "name": i.filename,
                    "reportDate": i.report_date.isoformat(),
                    "status": i.review_status,
                    "earlierEvidence": i.report_date != day} for i in images],
    }


def reconcile_known_permits(db, *, actor: str = "DESPATCH_AUTOMATIC_PERMIT_MASTER",
                            start_day: date = OPEN_DAY, end_day: date | None = None):
    """Repair only missing buyer/destination/material from exact prior permit.

    Historical E-Pass rows are read-only. Each permit is validated before any
    of its missing categories are changed, and every repair is audit logged.
    """
    from app.routers.tiom_despatch import DespatchTrip, DespatchAudit
    if start_day < OPEN_DAY:
        start_day = OPEN_DAY
    constraints = [DespatchTrip.report_date >= start_day,
                   DespatchTrip.status == "ACTIVE"]
    if end_day:
        constraints.append(DespatchTrip.report_date <= end_day)
    targets = list(db.scalars(select(DespatchTrip).where(*constraints)
                              .order_by(DespatchTrip.report_date, DespatchTrip.epass_no)))
    if not targets:
        return {"ok": True, "updatedTrips": 0, "updatedPermits": 0}
    # Read historic source data once and maintain it in chronological order,
    # so a newly verified permit works for later days as well.
    historic = list(db.scalars(select(DespatchTrip).where(
        DespatchTrip.report_date < start_day, DespatchTrip.status == "ACTIVE"
    )))
    by_permit = defaultdict(list)
    for item in historic:
        by_permit[item.permit_no].append(item)
    days = defaultdict(list)
    for item in targets:
        days[item.report_date].append(item)
    changed = set()
    trip_count = 0
    for day in sorted(days):
        daily_by_permit = defaultdict(list)
        for item in days[day]:
            daily_by_permit[item.permit_no].append(item)
        for permit, entries in daily_by_permit.items():
            pending = [x for x in entries if any(not str(getattr(x, f) or "").strip()
                                                 for f in FIELDS)]
            if not pending:
                continue
            candidate = _group_candidate(by_permit.get(permit, []))
            if not candidate or not all(_matches_existing(x, candidate) for x in entries):
                continue
            permit_changed = []
            for trip in pending:
                fields = {}
                for field in FIELDS:
                    if not str(getattr(trip, field) or "").strip():
                        setattr(trip, field, candidate[field])
                        fields[field] = candidate[field]
                if fields:
                    permit_changed.append((trip.epass_no, fields))
            if permit_changed:
                db.add(DespatchAudit(
                    actor=actor, action="PERMIT_SOURCE_MAPPING",
                    entity_key=permit, reason="Verified exact prior permit E-Pass categories",
                    before_json=None,
                    after_json=json.dumps({"reportDate": day.isoformat(),
                                           "sourceHistoryRows": candidate["historicalRows"],
                                           "tripCount": len(permit_changed),
                                           "changedEPasses": [x[0] for x in permit_changed[:10]],
                                           "sourceFields": {k: candidate[k] for k in FIELDS}}),
                ))
                changed.add(permit)
                trip_count += len(permit_changed)
        for item in days[day]:
            # Pending entries without sources are ignored by candidate validation.
            by_permit[item.permit_no].append(item)
    if trip_count:
        db.commit()
    return {"ok": True, "updatedTrips": trip_count, "updatedPermits": len(changed)}


def apply_confirmed_category(db, *, actor: str, report_date: date, permit_no: str,
                             category_index: int, document_id: str, expected_trips: int,
                             apply_to_related_dates: bool = True):
    """One verified AMNS classification for one permit/day; no weight edits."""
    from app.routers.tiom_despatch import (
        DespatchTrip, DespatchDocument, DespatchAudit,
    )
    if report_date < OPEN_DAY:
        raise ValueError("Completed reporting dates are protected")
    if not 0 <= category_index < len(DESTINATION_BUCKETS):
        raise ValueError("Choose an approved client report category")
    doc = db.get(DespatchDocument, document_id)
    if not doc or not doc.report_date or doc.report_date > report_date:
        raise ValueError("Select an existing AMNS image dated on or before the E-Pass reporting date")
    # The selected-day count must match the screen before touching anything.
    selected = list(db.scalars(select(DespatchTrip).where(
        DespatchTrip.report_date == report_date,
        DespatchTrip.permit_no == permit_no,
        DespatchTrip.status == "ACTIVE",
    )))
    if not selected or len(selected) != expected_trips:
        raise ValueError("Permit trip count changed; refresh before confirmation")
    # An explicitly verified source image proves permit identity, not the
    # quantities on subsequent dates. Reuse its classification for the exact
    # same permit only, while preserving each E-Pass date, MT and status.
    first_day = max(OPEN_DAY, doc.report_date) if apply_to_related_dates else report_date
    rows = list(db.scalars(select(DespatchTrip).where(
        DespatchTrip.report_date >= first_day,
        DespatchTrip.report_date <= report_date,
        DespatchTrip.permit_no == permit_no,
        DespatchTrip.status == "ACTIVE",
    ).order_by(DespatchTrip.report_date, DespatchTrip.epass_no)))
    consignees = {normalized(x.consignee) for x in rows if x.consignee}
    if len(consignees) > 1:
        raise ValueError("This permit has inconsistent consignee data across dates; confirm each date separately")
    positive_quantities = {Decimal(str(x.permit_qty)) for x in rows
                           if x.permit_qty is not None and Decimal(str(x.permit_qty)) > 0}
    if len(positive_quantities) > 1:
        raise ValueError("This permit has inconsistent registered quantities across dates; confirm each date separately")
    choice = dict(zip(FIELDS, DESTINATION_BUCKETS[category_index]))
    from app.services.tiom_despatch_client_layout import material_normalized
    if material_normalized(choice["material_grade"], report_date) not in VALID_MATERIALS:
        raise ValueError("This destination bucket is not recognized by the material-wise report; choose a supported grade")
    # Confirmed customer mapping cannot overwrite known, contradictory source.
    for row in rows:
        if not _matches_existing(row, choice):
            raise ValueError("Existing source classification conflicts with this category; preserve original")
    changed = 0
    changed_epasses = []
    changed_dates = set()
    for row in rows:
        updated = False
        for key in FIELDS:
            if not str(getattr(row, key) or "").strip():
                setattr(row, key, choice[key])
                changed += 1
                updated = True
        if updated:
            changed_epasses.append(row.epass_no)
            changed_dates.add(row.report_date.isoformat())
    if changed:
        db.add(DespatchAudit(actor=actor, action="CONFIRM_AMNS_CATEGORY",
                            entity_key=permit_no,
                            reason="Operator-verified AMNS source category for exact permit " + doc.id,
                            before_json=None,
                            after_json=json.dumps({"reportDate": report_date.isoformat(),
                                                   "imageDate": doc.report_date.isoformat(),
                                                   "imageId": doc.id,
                                                   "categoryIndex": category_index,
                                                   "fields": choice,
                                                   "selectedDayTrips": len(selected),
                                                   "applyToRelatedDates": apply_to_related_dates,
                                                   "relatedTripsChecked": len(rows),
                                                   "changedTripCount": len(changed_epasses),
                                                   "changedDates": sorted(changed_dates),
                                                   "changedEPasses": changed_epasses[:20]})))
        db.commit()
    return {"ok": True, "permit": permit_no, "tripsChecked": len(selected),
            "relatedTripsChecked": len(rows), "changedTripCount": len(changed_epasses),
            "changedDates": sorted(changed_dates), "imageDate": doc.report_date.isoformat(),
            "changedFields": changed, "category": choice}
