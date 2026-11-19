"""One-time, source-verified correction of historical TIOM Despatch fields.

No operation uses a guessed clock or quantity. Original Gmail attachments are
located by name then verified against their reviewed SHA-256 digests. The
existing E-Pass ledger must match on date, E-Pass, vehicle, tare/gross/net.
Only empty dispatch_time/permit_qty values are enriched. No new trips.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from email.utils import parseaddr
from hashlib import sha256
import json
import logging

from sqlalchemy import select

from app.db import SessionLocal
from app.routers.tiom_despatch import DespatchAudit, DespatchTrip, DespatchPermitDay, _trip
from app.services.tiom_despatch_source_adapters import parse_despatch_sources

log = logging.getLogger("nmtpl.despatch.repair")

# Immutable source fingerprints from approved TIOM MIS mailbox originals.
# These identify the one-time historical correction, NOT dynamic ERP masters.
SOURCE_FILES = (
    ("2026-11-01", "Date Wise 01-11-2026.xls",
     "1f0584c32bc72ee58286f009f3da4699cf3ef31e1c0e0ddcb6b89291100f5a77", 261),
    ("2026-11-02", "Datewise 02-11-2026.xls",
     "779f43c4cc7cc6b6fe551671d98392ce60114ec9905e4b5782a755e4c0b154c4", 331),
    ("2026-11-03", "Datewise 03-11-2026.xls",
     "80ec83a3ace2f2c6fcc64c25a0e2d9c0749518d5240470f87aecdab6038916c5", 475),
    ("2026-11-04", "Datewise 04-11-2026.xls",
     "08f90c90b3cbc60fbf9321440d8cb3ef62bfd6eb48d9ad7ff4efcb782369c9c0", 449),
)
MONTH_SOURCE = (
    "Trip Summary 18.11.26.xlsx",
    "08efd2d5130513c433564fa04dc006e812bcf3ceb7565023c42ad781a8703e0b",
)
AUDIT_DATE = date(2026, 11, 3)


def _gmail_file(service, filename, expected_hash):
    from app.services.tiom_despatch_mail import _attachment

    q = 'filename:"' + filename + '" after:2026/11/01 before:2026/11/20'
    messages = service.users().messages()
    listing = messages.list(userId="me", q=q, maxResults=30).execute()
    for summary in listing.get("messages", []):
        message_id = summary["id"]
        message = messages.get(userId="me", id=message_id, format="full").execute()
        stack = [message.get("payload") or {}]
        while stack:
            part = stack.pop()
            stack.extend(part.get("parts") or [])
            if part.get("filename") != filename:
                continue
            binary = _attachment(service, message_id, part)
            if sha256(binary).hexdigest() == expected_hash:
                return binary
    raise ValueError("Verified Gmail source unavailable or hash changed: " + filename)


def _match(source, saved):
    expected = _trip(source)
    return (
        saved.report_date == expected["report_date"]
        and saved.vehicle_no.strip().upper() == expected["vehicle_no"].strip().upper()
        and abs(Decimal(saved.net_mt) - expected["net_mt"]) <= Decimal(".025")
        and abs(Decimal(saved.tare_mt) - expected["tare_mt"]) <= Decimal(".025")
        and abs(Decimal(saved.gross_mt) - expected["gross_mt"]) <= Decimal(".025")
    )


def _source_day(binary, filename, iso_day, expected_count):
    data = [
        row for row in parse_despatch_sources(binary, filename)
        if row.get("_role") == "detailed" and row.get("report_date") == iso_day
    ]
    if len(data) != expected_count:
        raise ValueError(
            f"{filename}: expected {expected_count} exact-day E-Passes, got {len(data)}"
        )
    unique = {row["epass_no"].upper().strip() for row in data}
    if len(unique) != expected_count:
        raise ValueError(filename + ": repeated E-Pass IDs")
    if any(not str(row.get("dispatch_time") or "").strip() for row in data):
        raise ValueError(filename + ": a source WB time is missing")
    return data


def _source_month_day(binary, filename):
    # The monthly workbook has both daily and Cummulative sheets. Use ONLY
    # the individual 03.11.26 worksheet, never double-count cumulative rows.
    rows = [
        row for row in parse_despatch_sources(binary, filename)
        if row.get("_role") == "detailed"
        and row.get("report_date") == AUDIT_DATE.isoformat()
        and row.get("source", "").endswith("/ 03.11.26")
    ]
    if len(rows) != 475 or len({r["epass_no"].upper().strip() for r in rows}) != 475:
        raise ValueError("Approved November monthly source did not contain 475 unique 3-Nov E-Passes")
    return rows


def _audit(db, action, key, details):
    db.add(DespatchAudit(
        actor="DESPATCH_VERIFIED_SOURCE_REPAIR",
        action=action, entity_key=key,
        reason="One-time verified original Gmail source; only missing report fields enriched",
        before_json=None, after_json=json.dumps(details, sort_keys=True),
    ))


def _approved_neighbor_quantity(db, source_rows):
    """Only one unchanged, CONFIRMED full-permit quantity across neighboring dates.

    Buyer, destination and grade must match the monthly source. The same
    consignee identity must also occur on the confirmed source date.
    """
    from app.services.tiom_despatch_client_layout import normalized, material_normalized
    by_permit = defaultdict(list)
    for r in source_rows:
        by_permit[r["permit_no"].upper().strip()].append(r)
    candidates = list(db.scalars(select(DespatchPermitDay).where(
        DespatchPermitDay.permit_no.in_(list(by_permit)),
        DespatchPermitDay.review_status == "CONFIRMED",
        DespatchPermitDay.permit_qty > 0,
        DespatchPermitDay.report_date >= date(2026, 11, 1),
        DespatchPermitDay.report_date <= date(2026, 11, 18),
    )))
    result = {}
    for permit, entries in by_permit.items():
        approved = [p for p in candidates if p.permit_no.upper().strip() == permit]
        amounts = {Decimal(p.permit_qty) for p in approved if Decimal(p.permit_qty) > 0}
        if len(amounts) != 1:
            continue
        desired = {
            (normalized(r.get("buyer")), normalized(r.get("destination")),
             material_normalized(r.get("material_grade"), AUDIT_DATE))
            for r in entries
        }
        if len(desired) != 1:
            continue
        from app.routers.tiom_despatch import _amns_buyer, _amns_material
        source_consignees = {normalized(r.get("consignee")) for r in entries}
        if len(source_consignees) != 1:
            continue
        for p in approved:
            try:
                category = (
                    normalized(_amns_buyer(p.buyer)), normalized(p.destination),
                    material_normalized(_amns_material(p.material,p.grade_percent,p.report_date),
                                        p.report_date),
                )
            except ValueError:
                continue
            if category not in desired:
                continue
            other_consignees = {
                normalized(x.consignee) for x in db.scalars(
                    select(DespatchTrip).where(
                        DespatchTrip.report_date == p.report_date,
                        DespatchTrip.permit_no == permit,
                    )
                ) if x.consignee
            }
            if other_consignees == source_consignees:
                result[permit] = next(iter(amounts))
                break
    return result


def apply_verified_source_fields(db, days, month):
    """Preflight the entire source and live ledger before mutating any row."""
    incoming = {}
    for day, records in days.items():
        for row in records:
            key = row["epass_no"].strip().upper()
            if key in incoming:
                raise ValueError("Duplicate original source E-Pass across dates " + key)
            incoming[key] = row

    saved = {
        x.epass_no.upper().strip(): x
        for x in db.scalars(select(DespatchTrip).where(
            DespatchTrip.report_date.between(date(2026, 11, 1),date(2026, 11, 4))
        ).with_for_update())
    }
    if len(incoming) != 1516:
        raise ValueError("Source count not 1,516")
    if not set(incoming).issubset(saved):
        raise ValueError("Live ledger missing validated source E-Passes: "
                         + str(len(set(incoming) - set(saved))))
    for key, source in incoming.items():
        row = saved[key]
        if not _match(source, row):
            raise ValueError("Live date/vehicle/weights mismatch for " + key)
        prior = str(row.dispatch_time or "").strip()
        newer = str(source["dispatch_time"]).strip()
        if prior and prior != newer:
            raise ValueError("Existing WB Time conflicts for " + key)

    # A separate MIS monthly report supplies full-permit quantities. Never
    # insert a new permit or infer the limit from summed dispatch tonnage.
    monthly = {r["epass_no"].upper().strip(): r for r in month}
    if len(monthly) != 475:
        raise ValueError("Duplicate 03-Nov monthly E-Pass")
    group_quantities = defaultdict(set)
    for source in month:
        value = Decimal(str(source.get("permit_qty") or "0"))
        if value > 0:
            group_quantities[source["permit_no"].upper().strip()].add(value)
    if any(len(amounts) != 1 for amounts in group_quantities.values()):
        raise ValueError("Monthly permit quantity changed within a single permit")
    for key, source in monthly.items():
        row = saved.get(key)
        if not row or not _match(source, row):
            raise ValueError("Approved 03-Nov permit source mismatch " + key)
        source_qty = Decimal(str(source.get("permit_qty") or "0"))
        if source_qty < 0:
            raise ValueError("Negative permit qty in approved report " + key)
        prior = Decimal(str(row.permit_qty or 0))
        if source_qty > 0 and prior > 0 and prior != source_qty:
            raise ValueError("Existing permit quantity conflicts with report for " + key)

    neighbor = _approved_neighbor_quantity(db, month)
    qty_updates = 0
    time_updates = 0
    skipped_permits = set()
    qty_permit_values = defaultdict(set)
    for key, source in monthly.items():
        row = saved[key]
        value = Decimal(str(source.get("permit_qty") or "0"))
        if value <= 0:
            value = neighbor.get(source["permit_no"].upper().strip(),Decimal("0"))
        if value <= 0 and Decimal(str(row.permit_qty or "0")) > 0:
            # Keep an existing approved row value rather than treating that
            # permit as unresolved on an incomplete historical source.
            value = Decimal(str(row.permit_qty))
        if value > 0:
            qty_permit_values[row.permit_no.upper()].add(value)
        else:
            skipped_permits.add(row.permit_no.upper())
        if value > 0 and not Decimal(str(row.permit_qty or "0")):
            row.permit_qty = value
            qty_updates += 1

    for key, source in incoming.items():
        row = saved[key]
        if not str(row.dispatch_time or "").strip():
            row.dispatch_time = source["dispatch_time"].strip()
            time_updates += 1

    _audit(db, "WB_TIME_SOURCE_REPAIR", "2026-11-01..04", {
        "matched": len(incoming),"filled": time_updates,
        "originalAttachments": [s[1] for s in SOURCE_FILES]
    })
    _audit(db, "PERMIT_QTY_SOURCE_REPAIR", "2026-11-03", {
        "matched": len(month), "filled": qty_updates,
        "verifiedPermitValues": {k: sorted(str(v) for v in s)
                                for k,s in qty_permit_values.items()},
        "unresolvedPermitNumbers": sorted(skipped_permits),
        "monthlySource": MONTH_SOURCE[0],
    })
    db.commit()
    return {"matchedWb":len(incoming),"wbFilled":time_updates,
            "matchedQty":len(month),"qtyFilled":qty_updates,
            "unresolved":sorted(skipped_permits)}


def repair_nov_despatch_fields():
    """Runs once on deployment, idempotent and nonfatal to service startup."""
    from app.routers.automation import _prepare_gmail_token
    from scripts.wb_gmail_worker import gmail_service

    with SessionLocal() as db:
        found = set(db.scalars(select(DespatchAudit.action).where(
            DespatchAudit.action.in_(
                ["WB_TIME_SOURCE_REPAIR","PERMIT_QTY_SOURCE_REPAIR"]
            ),
            DespatchAudit.actor == "DESPATCH_VERIFIED_SOURCE_REPAIR",
        )))
        if len(found) == 2:
            log.info("TIOM_DESPATCH_NOV_SOURCE_REPAIR_ALREADY_APPLIED")
            return {"alreadyApplied":True}
    _prepare_gmail_token()
    service = gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    if (profile.get("emailAddress") or "").strip().lower() != "mistiom@nmtpl.com":
        raise ValueError("Historical Despatch correction requires authorized MIS Gmail")
    days = {}
    for iso_day,filename,digest,count in SOURCE_FILES:
        binary = _gmail_file(service, filename,digest)
        days[iso_day] = _source_day(binary,filename,iso_day,count)
    filename,digest = MONTH_SOURCE
    month = _source_month_day(_gmail_file(service,filename,digest),filename)
    with SessionLocal() as db:
        result = apply_verified_source_fields(db,days,month)
    log.warning("TIOM_DESPATCH_NOV_SOURCE_REPAIR_RESULT %s",json.dumps(result,sort_keys=True))
    return result
