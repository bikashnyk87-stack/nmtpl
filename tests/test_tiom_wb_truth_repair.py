"""WB MIS regression: exact authoritative links, idempotent repair and future protection."""
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Product, Equipment, Location, WbMovement, WbImportBatch, AuditLog
from app.site_models import TiomMisReport, TiomMisTripRow, TiomMisTripDetail, TiomMisReconciliation
from app.services.tiom_wb_truth import (repair_saved_wb_linked_mis,
                                        canonical_wb_product)


DAY=date(2026,10,11)
CRUSHER="Fines 0-10 mm+60%-62%FeCrus.Thakurani"
SCREEN="Fines 0-10 mm+60%-62%FeScr.Thakurani"


def populate(db):
    db.add_all([
        Equipment(machine_id="DTE-01",type="Tipper",group="TRANSPORT"),
        Location(location_id="WRONG",location_name="WRONG PIT"),
        Location(location_id="CRUSHER-PLANT",location_name="CRUSHER PLANT"),
        Location(location_id="S3",location_name="S3"),
        Product(product_id="P-CFN",name=SCREEN,active=True),
        Product(product_id="P-OB",name="Overburden",active=True),
        WbImportBatch(batch_id="batch-new",operating_date=DAY,shift="A",
                      file_name="WB.xlsx",file_hash="test",status="CONFIRMED",
                      confirmed_at=datetime(2026,10,11,12,tzinfo=timezone.utc),valid_rows=4,review_rows=1),
        WbImportBatch(batch_id="batch-old",operating_date=DAY,shift="A",
                      file_name="old.xlsx",file_hash="old",status="REPLACED",
                      confirmed_at=datetime(2026,10,11,11,tzinfo=timezone.utc),valid_rows=1,review_rows=0),
    ])
    db.flush()
    cases=[
        ("good","batch-new","VALID","SUBMITTED","DTE-01","P-OB",Decimal("41.76"),True),
        ("already","batch-new","VALID","SUBMITTED","DTE-01","P-CFN",Decimal("38"),True),
        ("void","batch-new","VALID","VOID","DTE-01","P-OB",Decimal("41.76"),True),
        ("draft","batch-new","VALID","DRAFT","DTE-01","P-OB",Decimal("41.76"),True),
        ("review","batch-new","REVIEW","SUBMITTED","DTE-01","P-OB",Decimal("41.76"),True),
        ("superseded","batch-old","VALID","SUBMITTED","DTE-01","P-OB",Decimal("41.76"),True),
        ("field","batch-new","VALID","SUBMITTED","DTE-01","P-OB",Decimal("45"),False),
    ]
    for ix,(key,batch,status,report_status,vehicle,material,qty,link) in enumerate(cases):
        db.add(WbMovement(movement_key="wb-"+key,batch_id=batch,operating_date=DAY,shift="A",
            movement_no=str(10000+ix),vehicle_raw="DTE-01",vehicle_id="DTE-01",
            material_code="TKCRF0010304",material_name=CRUSHER,
            source_raw="CRUSHER PLANT",destination_raw="S3",
            tare_kg=Decimal("16000"),gross_kg=Decimal("16000")+Decimal("41760"),
            net_kg=Decimal("41760"),weigh_at=datetime(2026,10,11,7,tzinfo=timezone.utc),
            row_status=status))
        db.add(TiomMisReport(report_id=key,operating_date=DAY,shift="A",
            vehicle_id=vehicle,status=report_status,entered_by="test"))
        db.add(TiomMisTripRow(row_id="row-"+key,report_id=key,row_no=1,
            material_raw="Overburden",source_raw="WRONG PIT",destination_raw="S3"))
        db.add(TiomMisTripDetail(row_id="row-"+key,material_id=material,
            source_location_id="WRONG",destination_location_id="S3",
            calculated_qty_mt=qty,factor_mt_per_trip=Decimal("45")))
        if link:
            db.add(TiomMisReconciliation(reconciliation_id="rec-"+key,
                row_id="row-"+key,wb_movement_key="wb-"+key,
                reconciled_by="test",match_status="MATCHED"))
    db.flush()


def test_correct_only_exact_active_wb_links_and_preserve_manual_void_review():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        populate(db)
        result=repair_saved_wb_linked_mis(db)
        assert result["counts"]["UPDATED"]==3, result
        assert result["counts"]["WB_NOT_VALID"]==1
        assert result["counts"]["VOID_REPORT"]==1
        assert result["counts"]["SUPERSEDED_BATCH"]==1
        records={x.row_id:x for x in db.scalars(select(TiomMisTripDetail))}
        wb_product=db.get(Product,records["row-good"].material_id)
        assert wb_product.name==CRUSHER
        for key in ["good","already","draft"]:
            entry=records["row-"+key]
            assert entry.material_id==wb_product.product_id
            assert entry.calculated_qty_mt==Decimal("41.76")
            assert entry.factor_mt_per_trip is None
            assert entry.source_location_id=="CRUSHER-PLANT"
        for key in ["void","review","superseded","field"]:
            assert records["row-"+key].material_id=="P-OB"
            assert records["row-"+key].source_location_id=="WRONG"
        assert records["row-field"].calculated_qty_mt==Decimal("45")
        db.flush()
        assert repair_saved_wb_linked_mis(db)["counts"]["UPDATED"]==0
        logs=list(db.scalars(select(AuditLog).where(AuditLog.action=="TIOM_WB_SAVED_TRIP_CORRECTED")))
        assert len(logs)==3
        assert any('"wbMovementKey": "wb-good"' in x.detail for x in logs)
    engine.dispose()


def test_distinct_wb_name_does_not_reuse_mis_wrong_material_alias():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Product(product_id="P-CFN",name=SCREEN))
        db.flush()
        wb=WbMovement(movement_key="x",batch_id="b",operating_date=DAY,shift="A",
            movement_no="m",material_code="TKCRF0010304",material_name=CRUSHER,
            source_raw="CRUSHER PLANT",destination_raw="S3",
            vehicle_raw="DTE-01",tare_kg=Decimal("1"),gross_kg=Decimal("1000"),
            net_kg=Decimal("999"),row_status="VALID")
        p=canonical_wb_product(db,wb)
        assert p.product_id!="P-CFN"
        assert p.name==CRUSHER
        assert canonical_wb_product(db,wb).product_id==p.product_id
        assert db.get(Product,"P-CFN").name==SCREEN
    engine.dispose()


def test_new_entry_uses_strict_confirmed_wb_fields():
    from pathlib import Path
    api=(Path(__file__).parents[1]/"app/routers/webapp.py").read_text("utf-8")
    js=(Path(__file__).parents[1]/"app/static/tiom_phase1.js").read_text("utf-8")
    assert "material_id=expected_material" in api
    assert "source_id=expected_source" in api
    assert "dest_id=expected_dest" in api
    assert "selected material differs from confirmed WB" in api
    assert "Source conflicts with confirmed WB" in api
    assert "Destination conflicts with confirmed WB" in api
    assert "readOnly=true" in js
    assert "materialLabel" in js
