"""Read-only PC Despatch mirror verification; never mutates WB or TIOM data."""
from __future__ import annotations
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from app.config import settings
from app.db import engine

ROOT=Path(__file__).resolve().parents[1]
TABLES=("tiom_despatch_trip","tiom_despatch_sender",
        "tiom_despatch_permit_day","tiom_despatch_audit")


def status():
    host=(make_url(settings.database_url).host or "").lower().strip()
    if host not in ("127.0.0.1","localhost","::1"):
        raise RuntimeError("Refusing to inspect non-local PostgreSQL host")
    with engine.connect() as conn:
        present=set(inspect(conn).get_table_names())
        counts={name:int(conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar() or 0)
                if name in present else None for name in TABLES}
        days=[]
        if "tiom_despatch_trip" in present:
            days=[dict(day=str(row.day),trips=int(row.trips),mt=str(row.mt))
                  for row in conn.execute(text("""
                    SELECT report_date AS day, COUNT(*) AS trips,
                           COALESCE(SUM(net_mt),0) AS mt
                    FROM tiom_despatch_trip
                    WHERE status='ACTIVE' AND report_date>=DATE '2026-10-01'
                    GROUP BY report_date ORDER BY report_date DESC LIMIT 7
                  """))]
    cursor_path=ROOT/"data"/"render_sync_state.json"
    replica_path=ROOT/"data"/"render_despatch_backfill.json"
    cursor=json.loads(cursor_path.read_text(encoding="utf-8")) if cursor_path.exists() else {}
    replica=json.loads(replica_path.read_text(encoding="utf-8")) if replica_path.exists() else {}
    return {"database":"PC local", "tables":counts,"recentDays":days,
            "watermark":cursor.get("last_change_id"),
            "originalBaselineComplete":cursor.get("baseline_complete"),
            "despatchBackfillComplete":all((replica.get("completed") or {}).get(t) for t in TABLES),
            "despatchBackfillTables":replica.get("completed",{})}


def main():
    report=status()
    print(json.dumps(report,indent=2))
    if any(count is None for count in report["tables"].values()):
        return 2
    if not report["despatchBackfillComplete"]:
        return 3
    return 0


if __name__=="__main__":
    raise SystemExit(main())
