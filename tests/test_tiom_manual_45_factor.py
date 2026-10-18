"""Sub-grade / Lumps / Boulder factor and historical repair regression tests."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AuditLog, Product
from app.site_models import (TiomMisReport, TiomMisTripRow,
                             TiomMisTripDetail, TiomMisReconciliation,
                             TiomTripFactor)
from app.routers.webapp import (_ensure_tiom_trip_factors, _tiom_material_factor,
                                backfill_tiom_manual_material_quantities)
from app.services.tiom_manual_material import canonical_manual_45_material


def test_material_spelling_and_safe_nonmatches():
    samples=[
        ("Sub-grade","SUBGRADE"),("SUB_GRADE","SUBGRADE"),("SUBGRADE DUMP","SUBGRADE"),
        ("Boulder","BOULDER"),("Boulders","BOULDER"),("ROM_LUMPS","ROM_LUMPS"),
        ("LUMPS","ROM_LUMPS"),("ROM Lumps","ROM_LUMPS"),
        ("CLO 10-40",None),("ROM",None),("Spillage",None),
    ]
    for material, expected in samples:
        assert canonical_manual_45_material(material,material)==expected


def test_factor_resolution_prefers_shared_lumps_rule_over_generic_rom():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        _ensure_tiom_trip_factors(db)
        db.add(TiomTripFactor(factor_id="custom-rom",material_code="ROM",
            factor_mt_per_trip=Decimal("33"),effective_from=date(2026,10,1),
            effective_to=None,active=True))
        db.flush()
        for product in [
            SimpleNamespace(product_id="LUMPS",name="Lumps"),
            SimpleNamespace(product_id="ROM_LUMPS",name="ROM Lumps"),
            SimpleNamespace(product_id="SUB-GRADE",name="Sub-grade"),
            SimpleNamespace(product_id="BOULDER",name="Boulder"),
        ]:
            factor,qty=_tiom_material_factor(db,product,date(2026,10,11))
            assert factor is not None and qty==Decimal("45"),product
        _,qty=_tiom_material_factor(db,SimpleNamespace(product_id="ROM",name="ROM"),date(2026,10,11))
        assert qty==Decimal("33")
    engine.dispose()


def test_backfill_only_missing_manual_nonvoid_nonwb_and_is_idempotent():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        materials=[("p1","Sub-grade"),("p2","Lumps"),("p3","ROM Lumps"),
                   ("p4","Boulder"),("p5","ROM"),("p6","CLO 10-40")]
        for key,name in materials:
            db.add(Product(product_id=key,name=name))
        entries=[("s1","p1","SUBMITTED",None,False),
                 ("s2","p2","SUBMITTED",None,False),
                 ("s3","p4","DRAFT",None,False),
                 ("s4","p3","SUBMITTED",Decimal("99"),False),
                 ("s5","p1","VOID",None,False),
                 ("s6","p2","SUBMITTED",None,True),
                 ("s7","p5","SUBMITTED",None,False),
                 ("s8","p6","SUBMITTED",None,False)]
        for idx,(rid,prod,status,qty,linked) in enumerate(entries):
            db.add(TiomMisReport(report_id=rid,operating_date=date(2026,10,11),
                shift="A",vehicle_id="TEST-TIPPER",status=status,entered_by="test"))
            db.add(TiomMisTripRow(row_id="row"+rid,report_id=rid,
                row_no=1,material_raw=next(n for k,n in materials if k==prod)))
            db.add(TiomMisTripDetail(row_id="row"+rid,material_id=prod,
                calculated_qty_mt=qty,factor_mt_per_trip=None))
            if linked:
                db.add(TiomMisReconciliation(reconciliation_id="rec"+rid,
                    row_id="row"+rid,wb_movement_key="TEST-WB",
                    match_status="MATCHED",reconciled_by="test"))
        db.flush()
        result=backfill_tiom_manual_material_quantities(db)
        assert result["updated"]==3
        assert result["byMaterial"]=={"SUBGRADE":1,"ROM_LUMPS":1,"BOULDER":1}
        assert backfill_tiom_manual_material_quantities(db)["updated"]==0
        values={x.row_id:(x.factor_mt_per_trip,x.calculated_qty_mt)
                for x in db.scalars(select(TiomMisTripDetail))}
        for key in ("s1","s2","s3"):
            assert values["row"+key]==(Decimal("45"),Decimal("45"))
        for key in ("s5","s6","s7","s8"):
            assert values["row"+key]==(None,None)
        assert values["rows4"]==(None,Decimal("99"))
        logs=list(db.scalars(select(AuditLog).where(
            AuditLog.action=="TIOM_MIS_MANUAL_FACTOR_BACKFILL")))
        assert len(logs)==3
    engine.dispose()
