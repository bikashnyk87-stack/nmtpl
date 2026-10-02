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
    for row in batch['vehicles']:
        current = db.get(VolvoVehicle, row['vin'])
        if current is None:
            current = VolvoVehicle(vin=row['vin'])
            db.add(current)
        current.payload, current.last_seen = row, now
    seen = set()
    for kind in ('vehiclepositions', 'vehiclestatuses'):
        for row in batch[kind]:
            created = report_time(row)
            if created is None:
                raise VolvoError('A Volvo report has no valid creation timestamp; no data saved.')
            digest = hashlib.sha256((kind + json.dumps(row, sort_keys=True, separators=(',', ':'))).encode()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            if db.get(VolvoReport, digest) is None:
                db.add(VolvoReport(digest=digest, vin=row['vin'], kind=kind, created_at=created, fetched_at=now, payload=row))
    db.add(VolvoSync(id=str(uuid.uuid4()), completed_at=now, counts=counts))
    db.commit()
    return counts

def latest_reports(db):
    ranked = select(VolvoReport.digest, func.row_number().over(
        partition_by=(VolvoReport.vin, VolvoReport.kind),
        order_by=(VolvoReport.created_at.desc(), VolvoReport.fetched_at.desc(), VolvoReport.digest.desc())
    ).label('rank')).subquery()
    return db.scalars(select(VolvoReport).join(ranked, VolvoReport.digest == ranked.c.digest).where(ranked.c.rank == 1)).all()
