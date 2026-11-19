"""One-time Despatch repair safeguards against incorrect production edits."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.routers.tiom_despatch import DespatchAudit, DespatchTrip, DespatchPermitDay
from app.services.tiom_despatch_nov_source_repair import (
    SOURCE_FILES, _match, apply_verified_source_fields,
)


def setup_case():
    engine = create_engine(
        "sqlite://",connect_args={"check_same_thread":False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine,tables=[
        DespatchTrip.__table__, DespatchAudit.__table__,DespatchPermitDay.__table__
    ])
    db=Session(engine)
    originals={}
    monthly=[]
    for day,_,_,count in SOURCE_FILES:
        originals[day]=[]
        for i in range(1,count+1):
            epass=f"L112600143{day[-2:]}/{i}"
            permit="L112600143"
            if day=="2026-11-03" and i<=43:
                permit="L102604966"
                epass=f"L102604966/{i}"
            row={
                "epass_no":epass,"permit_no":permit,"report_date":day,
                "vehicle_no":"OD09AA1234","tare_mt":"15.000",
                "gross_mt":"45.000","net_mt":"30.000",
                "dispatch_time":"10:17:30:927AM",
                "buyer":"Self","destination":"DABUNA",
                "material_grade":"S.Fines(60-62)",
                "consignee":"ARCELOR MITTAL NIPPON STEEL INDIA LIMITED",
            }
            originals[day].append(row)
            db.add(DespatchTrip(
                epass_no=epass, report_date=date.fromisoformat(day),
                permit_no=permit, vehicle_no=row["vehicle_no"],
                tare_mt=Decimal("15"),gross_mt=Decimal("45"),
                net_mt=Decimal("30"), dispatch_time="",
                permit_qty=Decimal("0"),status="ACTIVE",
                buyer="Self",destination="DABUNA",material_grade="S.Fines(60-62)",
                consignee=row["consignee"],
            ))
            if day=="2026-11-03":
                monthly.append({
                    **row,
                    "source":"Trip Summary 18.11.26.xlsx / 03.11.26",
                    "permit_qty":"8000.620" if i<=43 else "",
                })
    db.commit()
    return engine,db,originals,monthly


def test_exact_source_matches_populate_only_missing_wb_and_approved_qty():
    engine,db,days,monthly=setup_case()
    try:
        initial=db.scalar(select(DespatchTrip).where(
            DespatchTrip.epass_no=="L102604966/1"))
        assert initial.dispatch_time==""
        result=apply_verified_source_fields(db,days,monthly)
        assert result["matchedWb"]==1516
        assert result["wbFilled"]==1516
        assert result["matchedQty"]==475
        assert result["qtyFilled"]==43
        assert "L112600143" in result["unresolved"]
        saved=db.scalar(select(DespatchTrip).where(
            DespatchTrip.epass_no=="L102604966/1"))
        assert saved.dispatch_time=="10:17:30:927AM"
        assert saved.permit_qty==Decimal("8000.620")
        assert saved.net_mt==Decimal("30.000")
        assert saved.gross_mt==Decimal("45.000")
        assert saved.tare_mt==Decimal("15.000")
        assert saved.vehicle_no=="OD09AA1234"
        assert db.query(DespatchTrip).count()==1516
        assert db.query(DespatchAudit).count()==2
        unresolved=db.scalar(select(DespatchTrip).where(
            DespatchTrip.epass_no=="L11260014303/100"))
        assert unresolved.permit_qty==Decimal("0.000")
        assert unresolved.dispatch_time=="10:17:30:927AM"
    finally:
        db.close();engine.dispose()


def test_mismatched_vehicle_blocks_all_writes():
    engine,db,days,monthly=setup_case()
    try:
        days["2026-11-04"][0]["vehicle_no"]="OD99INVALID"
        with pytest.raises(ValueError,match="mismatch"):
            apply_verified_source_fields(db,days,monthly)
        assert db.query(DespatchAudit).count()==0
        assert db.query(DespatchTrip).filter(DespatchTrip.dispatch_time=="").count()==1516
    finally:
        db.close();engine.dispose()
