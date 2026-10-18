"""WB-linked TIOM MIS truth enforcement and audited historic correction.

Never infer WB membership from matching weights; only exact saved movement keys
may update trips. No field-only, VOID, review, or superseded rows are rewritten.
"""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha1
import json
import re

from sqlalchemy import select

from app.models import AuditLog, Equipment, Product, WbImportBatch, WbMovement
from app.site_models import (TiomMisTripRow, TiomMisTripDetail, TiomMisReport,
                             TiomMisReconciliation)
from app.services.tiom_erp import _norm, resolve_location_id, vehicle_matches


def _audit(db, action, entity, entity_id, detail):
    db.add(AuditLog(created_at=datetime.now(timezone.utc),actor="SYSTEM",
                    action=action,entity=entity,entity_id=str(entity_id),
                    detail=json.dumps(detail,default=str,sort_keys=True)))


def _wb_identifier(wb):
    """Keep identities different when same SAP code acquires a different name."""
    code=re.sub(r'[^A-Z0-9]+','',str(wb.material_code or '').upper())
    name=_norm(wb.material_name)
    digest=sha1((code+"|"+name).encode()).hexdigest()[:10].upper()
    return ("WB-"+code[:34]+"-"+digest)[:50]


def canonical_wb_product(db,wb,create=True):
    """Choose an exact-name Product or a distinct immutable WB-code Product.

    Existing MaterialAlias rows and fuzzy substring matches are never trusted
    when the resolved product's name contradicts the WB material name.
    """
    wbname=str(wb.material_name or '').strip()
    if not wbname:
        return None
    normalized=_norm(wbname)
    products=list(db.scalars(select(Product)))
    candidates=[p for p in products if _norm(p.name)==normalized and p.active]
    if len(candidates)==1:
        return candidates[0]
    # More than one product with same label is ambiguous: create an exact
    # code+name identity rather than picking the first arbitrary record.
    pid=_wb_identifier(wb)
    obj=db.get(Product,pid)
    if obj:
        if _norm(obj.name)!=normalized:
            raise ValueError(f"WB product ID collision for {pid}")
        if not obj.active:
            obj.active=True
        return obj
    if not create:
        return None
    obj=Product(product_id=pid,name=wbname,active=True,saleable=False,
                wb_material_codes=str(wb.material_code or '').strip())
    db.add(obj)
    db.flush()
    _audit(db,"TIOM_WB_PRODUCT_CANONICAL_CREATED","products",pid,
           {"wbMaterialCode":wb.material_code,"wbMaterialName":wbname,
            "reason":"Stable exact material identity; never override a different master label."})
    return obj


def validate_wb_truth(db,wb,report,equipment):
    """Read-only guards for which saved links can safely be corrected."""
    if wb is None:
        return "WB_MOVEMENT_MISSING"
    if wb.row_status!="VALID":
        return "WB_NOT_VALID"
    if report.status=="VOID":
        return "VOID_REPORT"
    if wb.operating_date!=report.operating_date or wb.shift!=report.shift:
        return "WB_SHIFT_DATE_MISMATCH"
    vehicle=equipment.get(report.vehicle_id)
    if not vehicle or not vehicle_matches(wb,vehicle):
        return "WB_VEHICLE_MISMATCH"
    if wb.net_kg is None or Decimal(wb.net_kg)<0:
        return "WB_INVALID_WEIGHT"
    if not (wb.material_name or "").strip():
        return "WB_NO_MATERIAL_NAME"
    return ""


def repair_saved_wb_linked_mis(db, operating_date=None, shift=None):
    """Idempotent repair of confirmed active WB links, with per-row audit.

    Only exact WB movement_key links for latest CONFIRMED batch, never joins
    by equal weights or approximated vehicle. Changes contain before/after.
    """
    batch_query=select(WbImportBatch).where(WbImportBatch.status=="CONFIRMED",WbImportBatch.confirmed_at.is_not(None))
    if operating_date is not None:
        batch_query=batch_query.where(WbImportBatch.operating_date==operating_date)
    if shift is not None:
        batch_query=batch_query.where(WbImportBatch.shift==shift)
    batches=list(db.scalars(batch_query.order_by(WbImportBatch.operating_date,WbImportBatch.shift,
               WbImportBatch.confirmed_at.desc(),WbImportBatch.batch_id.desc())))
    latest={}
    for batch in batches:
        latest.setdefault((batch.operating_date,batch.shift),batch.batch_id)
    rec_query=select(TiomMisReconciliation).where(TiomMisReconciliation.wb_movement_key.is_not(None))
    if operating_date is not None or shift is not None:
        rec_query=(rec_query.join(TiomMisTripRow,TiomMisTripRow.row_id==TiomMisReconciliation.row_id)
            .join(TiomMisReport,TiomMisReport.report_id==TiomMisTripRow.report_id))
        if operating_date is not None:
            rec_query=rec_query.where(TiomMisReport.operating_date==operating_date)
        if shift is not None:
            rec_query=rec_query.where(TiomMisReport.shift==shift)
    recs=list(db.scalars(rec_query)
    equipment={e.machine_id:e for e in db.scalars(select(Equipment))}
    result=Counter(); changed_by_date=Counter()
    material_cache={}; location_cache={}
    for rec in recs:
        row=db.get(TiomMisTripRow,rec.row_id)
        if row is None:
            result["NO_MIS_ROW"]+=1;continue
        rep=db.get(TiomMisReport,row.report_id)
        if rep is None:
            result["NO_MIS_REPORT"]+=1;continue
        wb=db.get(WbMovement,rec.wb_movement_key)
        reason=validate_wb_truth(db,wb,rep,equipment)
        if reason:
            result[reason]+=1;continue
        if latest.get((wb.operating_date,wb.shift))!=wb.batch_id:
            result["SUPERSEDED_BATCH"]+=1;continue
        detail=db.get(TiomMisTripDetail,rec.row_id)
        if detail is None:
            result["NO_MIS_DETAIL"]+=1;continue

        material_key=(wb.material_code or "",wb.material_name or "")
        if material_key not in material_cache:
            material_cache[material_key]=canonical_wb_product(db,wb)
        product=material_cache[material_key]
        if not product:
            result["PRODUCT_UNRESOLVED"]+=1;continue
        skey=("SOURCE",wb.source_raw or "")
        dkey=("DESTINATION",wb.destination_raw or "")
        if skey not in location_cache:
            location_cache[skey]=resolve_location_id(db,wb.source_raw,"SOURCE")
        if dkey not in location_cache:
            location_cache[dkey]=resolve_location_id(db,wb.destination_raw,"DESTINATION")
        source=location_cache[skey]
        destination=location_cache[dkey]
        if not source:
            result["SOURCE_UNRESOLVED"]+=1
        if not destination:
            result["DESTINATION_UNRESOLVED"]+=1
        expected=Decimal(wb.net_kg)/Decimal("1000")
        before={
            "materialId":detail.material_id,"qtyMt":str(detail.calculated_qty_mt) if detail.calculated_qty_mt is not None else None,
            "factorMtPerTrip":str(detail.factor_mt_per_trip) if detail.factor_mt_per_trip is not None else None,
            "sourceLocationId":detail.source_location_id,"destinationLocationId":detail.destination_location_id,
            "materialRaw":row.material_raw,"sourceRaw":row.source_raw,"destinationRaw":row.destination_raw,
        }
        # Never erase the location master ID if its WB alias is unresolved.
        detail.material_id=product.product_id
        detail.calculated_qty_mt=expected
        detail.factor_mt_per_trip=None
        if source:
            detail.source_location_id=source
        if destination:
            detail.destination_location_id=destination
        row.material_raw=wb.material_name or wb.material_code
        row.source_raw=wb.source_raw or ""
        row.destination_raw=wb.destination_raw or ""
        after={
            "materialId":detail.material_id,"qtyMt":str(detail.calculated_qty_mt),
            "factorMtPerTrip":None,
            "sourceLocationId":detail.source_location_id,"destinationLocationId":detail.destination_location_id,
            "materialRaw":row.material_raw,"sourceRaw":row.source_raw,"destinationRaw":row.destination_raw,
        }
        if before!=after:
            _audit(db,"TIOM_WB_SAVED_TRIP_CORRECTED","tiom_mis_trip_detail",rec.row_id,
                {"reportId":rep.report_id,"operatingDate":str(rep.operating_date),
                 "shift":rep.shift,"vehicleId":rep.vehicle_id,"wbMovementKey":wb.movement_key,
                 "wbMovementNo":wb.movement_no,"wbBatchId":wb.batch_id,
                 "wbMaterialCode":wb.material_code,"wbMaterialName":wb.material_name,
                 "before":before,"after":after,
                 "unresolvedLocations":[x for x,c in (("SOURCE",source),("DESTINATION",destination)) if not c]})
            result["UPDATED"]+=1
            changed_by_date[str(rep.operating_date)]+=1
        else:
            result["ALREADY_MATCHED"]+=1
    db.flush()
    return {"counts":dict(result),"correctedByDate":dict(sorted(changed_by_date.items())),"linkedRecordsChecked":len(recs)}
