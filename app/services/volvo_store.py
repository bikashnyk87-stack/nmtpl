import hashlib
import json
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, text, func
from app.volvo_models import VolvoVehicle, VolvoReport, VolvoSync
from app.services.volvo_client import ENDPOINTS, VolvoError, report_time

def collect(db, client):
    # A transaction-scoped lock prevents concurrent collectors on PostgreSQL.
    if db.bind.dialect.name == 'postgresql':
        if not db.execute(text('SELECT pg_try_advisory_xact_lock(867530920)')).scalar():
            raise VolvoError('Another Volvo collector is already running.')
    batch = {name: client.fetch(name) for name in ENDPOINTS}
    now = datetime.now(timezone.utc)
    counts = {name: len(rows) for name, rows in batch.items()}
    # Read each vehicle only once, and only UPDATE when Volvo changed it.
    # Previously every successful poll wrote last_seen for every vehicle.
    vins = [row['vin'] for row in batch['vehicles']]
    existing_vehicles = {
        item.vin: item for item in db.scalars(
            select(VolvoVehicle).where(VolvoVehicle.vin.in_(vins))
        )
    } if vins else {}
    changed_vehicles = 0
    for row in batch['vehicles']:
        current = existing_vehicles.get(row['vin'])
        if current is None:
            db.add(VolvoVehicle(vin=row['vin'], payload=row, last_seen=now))
            changed_vehicles += 1
        elif current.payload != row:
            current.payload, current.last_seen = row, now
            changed_vehicles += 1

    seen = set()
    candidates = []
    for kind in ('vehiclepositions', 'vehiclestatuses'):
        for row in batch[kind]:
            created = report_time(row)
            if created is None:
                raise VolvoError('A Volvo report has no valid creation timestamp; no data saved.')
            digest = hashlib.sha256((kind + json.dumps(row, sort_keys=True, separators=(',', ':'))).encode()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            candidates.append((digest,row['vin'],kind,created,row))

    # One indexed lookup replaces thousands of get() round-trips; preserve
    # original SHA256 identity, payload, kind, timestamps and history.
    existing_digests = set()
    for offset in range(0,len(candidates),500):
        keys=[x[0] for x in candidates[offset:offset+500]]
        existing_digests.update(
            db.scalars(select(VolvoReport.digest).where(VolvoReport.digest.in_(keys)))
        )
    new_reports=0
    for digest, vin, kind, created, row in candidates:
        if digest not in existing_digests:
            db.add(VolvoReport(digest=digest,vin=vin,kind=kind,
                               created_at=created,fetched_at=now,payload=row))
            new_reports+=1
    counts['changed_vehicles']=changed_vehicles
    counts['new_reports']=new_reports
    db.add(VolvoSync(id=str(uuid.uuid4()), completed_at=now, counts=counts))
    db.commit()
    return counts

def latest_reports(db):
    ranked = select(VolvoReport.digest, func.row_number().over(
        partition_by=(VolvoReport.vin, VolvoReport.kind),
        order_by=(VolvoReport.created_at.desc(), VolvoReport.fetched_at.desc(), VolvoReport.digest.desc())
    ).label('rank')).subquery()
    return db.scalars(select(VolvoReport).join(ranked, VolvoReport.digest == ranked.c.digest).where(ranked.c.rank == 1)).all()
