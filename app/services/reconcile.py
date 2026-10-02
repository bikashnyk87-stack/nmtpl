from __future__ import annotations
from collections import defaultdict
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import LoadTrip, WbMovement, LoadWbMatch, WbImportBatch, MaterialAlias
from app.services.wb_mapping import build_location_resolver

MATCH_WINDOW = timedelta(minutes=120)

def auto_reconcile(db: Session, operating_date, shift: str):
    location_resolver = build_location_resolver(db)
    trips = db.execute(
        select(LoadTrip).where(
            LoadTrip.operating_date == operating_date,
            LoadTrip.shift == shift,
            LoadTrip.vehicle_id.is_not(None),
            LoadTrip.loading_end_at.is_not(None),
            LoadTrip.status == "CLOSED",
        ).order_by(LoadTrip.vehicle_id, LoadTrip.loading_end_at)
    ).scalars().all()
    wb = db.execute(
        select(WbMovement).join(WbImportBatch, WbMovement.batch_id == WbImportBatch.batch_id).where(
            WbMovement.operating_date == operating_date,
            WbMovement.shift == shift,
            WbMovement.row_status == "VALID",
            WbImportBatch.status == "CONFIRMED",
        ).order_by(WbMovement.vehicle_id, WbMovement.weigh_at)
    ).scalars().all()

    existing_trip = set(db.execute(select(LoadWbMatch.trip_id)).scalars().all())
    existing_wb = set(db.execute(select(LoadWbMatch.movement_key)).scalars().all())

    by_vehicle_trip = defaultdict(list)
    by_vehicle_wb = defaultdict(list)
    for t in trips:
        if t.trip_id not in existing_trip:
            by_vehicle_trip[t.vehicle_id].append(t)
    for w in wb:
        if w.movement_key not in existing_wb and w.vehicle_id:
            by_vehicle_wb[w.vehicle_id].append(w)

    matched = []
    pending_trip = []
    pending_wb = []

    for vehicle in sorted(set(by_vehicle_trip) | set(by_vehicle_wb)):
        trows = by_vehicle_trip.get(vehicle, [])
        wrows = by_vehicle_wb.get(vehicle, [])
        wi = 0
        for trip in trows:
            while wi < len(wrows) and wrows[wi].weigh_at < trip.loading_end_at:
                pending_wb.append(wrows[wi])
                wi += 1
            if wi >= len(wrows):
                pending_trip.append(trip)
                continue
            movement = wrows[wi]
            delta = movement.weigh_at - trip.loading_end_at
            if delta > MATCH_WINDOW:
                pending_trip.append(trip)
                continue
            confidence = 70
            reasons = ["Date+Shift+Vehicle sequential match"]
            if trip.source_location_id and movement.source_raw:
                wb_source = location_resolver.resolve_raw(movement.source_raw, "SOURCE")
                if wb_source == trip.source_location_id:
                    confidence += 10; reasons.append("source aligned")
            if trip.destination_location_id and movement.destination_raw:
                wb_dest = location_resolver.resolve_raw(movement.destination_raw, "DESTINATION")
                if wb_dest == trip.destination_location_id:
                    confidence += 10; reasons.append("destination aligned")
            if trip.material_id and movement.material_code and trip.material_id.upper().replace("P-","") in movement.material_code.upper():
                confidence += 10; reasons.append("material aligned")
            match = LoadWbMatch(
                match_id=str(uuid4()), trip_id=trip.trip_id, movement_key=movement.movement_key,
                status="MATCHED" if confidence >= 80 else "LIKELY_MATCH",
                method="AUTO_SEQUENCE", confidence=confidence, reason="; ".join(reasons),
            )
            db.add(match); matched.append(match); wi += 1
        pending_wb.extend(wrows[wi:])
    return {
        "matched": len(matched),
        "field_without_wb": len(pending_trip),
        "wb_unmatched": len(pending_wb),
    }
