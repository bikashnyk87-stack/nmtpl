"""TIOM operational shifts and carefully scoped WB review correction.

TIOM uses 05-13, 13-21 and 21-05 Asia/Kolkata. SOCP/KOCP are untouched.
The five 11-Oct-2026 entries were independently verified against the raw WB
export. Only exact WB movement IDs in the active confirmed C batch can change.
"""
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
import json

from sqlalchemy import select

from app.models import ShiftMaster, WbImportBatch, WbMovement, AuditLog
from app.site_models import SiteShift
from app.services.time_context import TZ, now_local

TIMES = {"A": (time(5,0),time(13,0),1),
         "B": (time(13,0),time(21,0),2),
         "C": (time(21,0),time(5,0),3)}
DAY=date(2026,10,11)
# (WB movement number, vehicle, local physical weigh timestamp, net MT, source material)
EXCEPTIONS={
    "20264014112738":("DT-06", "2026-10-11 21:33:33",Decimal("51.52"),"ROM Thakurani"),
    "20264014112739":("DTV-32","2026-10-11 21:37:45",Decimal("50.38"),"ROM Thakurani"),
    "20264014112740":("DT-04", "2026-10-11 21:51:44",Decimal("48.94"),"Waste Rock Thakurani"),
    "20264014112741":("DT-14", "2026-10-11 21:53:02",Decimal("47.32"),"Waste Rock Thakurani"),
    "20264014112808":("DTE-02","2026-10-12 00:00:27",Decimal("40.78"),"Fines 0-10 mm+60%-62%FeScr.Thakurani"),
}

def _audit(db, action, key, payload):
    db.add(AuditLog(created_at=now_local(),actor="SYSTEM",action=action,
                    entity="wb_movement" if action.startswith("TIOM_WB") else "shift_master",
                    entity_id=str(key),detail=json.dumps(payload,sort_keys=True,default=str)))

def align_tiom_shifts(db):
    """Explicit correction authorized by mine: no other site shift is edited.

    ShiftMaster is TIOM's authoritative time source; mirror into SiteShift.
    """
    changes=[]
    for shift,(start,end,seq) in TIMES.items():
        master=db.get(ShiftMaster,shift)
        before=None if master is None else {"start":str(master.start_time),"end":str(master.end_time)}
        if master is None:
            master=ShiftMaster(shift=shift,start_time=start,end_time=end,scheduled_hours=8,active=True)
            db.add(master)
        else:
            master.start_time=start
            master.end_time=end
            master.scheduled_hours=8
            master.active=True
        site=db.get(SiteShift,{"site_id":"TIOM","shift":shift})
        if site is None:
            site=SiteShift(site_id="TIOM",shift=shift,shift_name="Shift "+shift,
                start_time=start,end_time=end,scheduled_hours=8,sequence_no=seq,active=True)
            db.add(site)
        else:
            site.start_time=start
            site.end_time=end
            site.scheduled_hours=8
            site.sequence_no=seq
            site.active=True
        if before != {"start":str(start),"end":str(end)}:
            _audit(db,"TIOM_SHIFT_MASTER_ALIGNED_0500_1300_2100",shift,
                   {"before":before,"after":{"start":str(start),"end":str(end)},
                    "reason":"Confirmed by mine: A 05-13, B 13-21, C 21-05."})
            changes.append(shift)
    db.flush()
    return {"aligned":changes,"effective":{"A":"05:00–13:00","B":"13:00–21:00","C":"21:00–05:00"}}

def resolve_oct11_five_wb_reviews(db):
    """Correct only five exact VALID-weight WB movements in current confirmed C.

    Never blindly reassign movement IDs or create duplicate trips/MIS rows.
    Keep original exception and old timestamp in AuditLog before overwriting.
    Reject any extra issue, ambiguous key, duplicate confirmed WB movement,
    wrong weight or vehicle, or unrecognized recorded material.
    """
    batches=list(db.scalars(select(WbImportBatch).where(
        WbImportBatch.operating_date==DAY,
        WbImportBatch.shift=="C",
        WbImportBatch.status=="CONFIRMED",
        WbImportBatch.confirmed_at.is_not(None)
    ).order_by(WbImportBatch.confirmed_at.desc())))
    if not batches:
        return {"corrected":0,"alreadyValid":0,"skipped":{"NO_CONFIRMED_C_BATCH":5}}
    batch=batches[0]
    candidates=list(db.scalars(select(WbMovement).where(
        WbMovement.batch_id==batch.batch_id,
        WbMovement.movement_no.in_(list(EXCEPTIONS)))))
    by_no={}
    for w in candidates:
        by_no.setdefault(w.movement_no,[]).append(w)
    stats=Counter();skip={}
    for number,(vehicle,stamp,tonnes,material) in EXCEPTIONS.items():
        matches=by_no.get(number,[])
        if len(matches)!=1:
            skip[number]="NOT_UNIQUE_IN_ACTIVE_C_BATCH" if matches else "NOT_IN_ACTIVE_C_BATCH"
            continue
        w=matches[0]
        expected_at=datetime.strptime(stamp,"%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        original_issue=str(w.issue or "")
        allowed_issue=(("Shift B != selected C" in original_issue and number!="20264014112808")
                       or (number=="20264014112808" and
                           "Movement Date 2026-10-11 != expected calendar date 2026-10-12" in original_issue))
        if w.row_status=="VALID":
            if (w.weigh_at and w.weigh_at.astimezone(TZ)==expected_at
                    and Decimal(w.net_kg)/1000==tonnes):
                stats["alreadyValid"]+=1
            else:
                skip[number]="VALID_BUT_TIMESTAMP_OR_WEIGHT_DIFFERS"
            continue
        if w.row_status!="REVIEW" or not allowed_issue:
            skip[number]="UNEXPECTED_REVIEW_REASON_OR_STATUS";continue
        # These are the only permissible issues; do not override weight, source,
        # location or other independently failed WB validation.
        issue_parts=[x.strip() for x in original_issue.split(";") if x.strip()]
        if any(not (x=="Shift B != selected C" or
                    x.startswith("Movement Date 2026-10-11 != expected calendar date 2026-10-12 for operating date 2026-10-11 / Shift C"))
               for x in issue_parts):
            skip[number]="OTHER_UNRESOLVED_WB_ERRORS";continue
        if (w.operating_date!=DAY or w.shift!="C" or w.vehicle_raw.strip().upper()!=vehicle
            or str(w.material_name or "").strip()!=material
            or Decimal(w.net_kg)/Decimal("1000")!=tonnes
            or w.gross_kg is None or w.tare_kg is None
            or Decimal(w.gross_kg)<=Decimal(w.tare_kg)
            or not w.source_raw or not w.destination_raw):
            skip[number]="RAW_WB_EVIDENCE_NOT_MATCHED";continue
        # Do not post twice if this movement number is VALID in another active
        # CONFIRMED batch, even with different batch-generated movement keys.
        duplicates=list(db.scalars(select(WbMovement).join(
            WbImportBatch,WbImportBatch.batch_id==WbMovement.batch_id
        ).where(WbMovement.movement_no==number,WbMovement.movement_key!=w.movement_key,
                WbMovement.row_status=="VALID",WbImportBatch.status=="CONFIRMED")))
        if duplicates:
            skip[number]="DUPLICATE_ACTIVE_CONFIRMED_WB";continue
        before={"status":w.row_status,"issue":w.issue,"weighAt":str(w.weigh_at),
                "movementKey":w.movement_key,"batchId":w.batch_id}
        w.weigh_at=expected_at
        w.row_status="VALID"
        # Preserve SAP label and old exception as an informational note.
        w.issue=("VERIFIED_TIOM_SHIFT_C_21_TO_05: 11-Oct operating date; "
                 "physical weighing "+stamp+" IST; original review: "+original_issue)
        batch.valid_rows=int(batch.valid_rows or 0)+1
        batch.review_rows=max(0,int(batch.review_rows or 0)-1)
        _audit(db,"TIOM_WB_REVIEW_SHIFT_C_VERIFIED",w.movement_key,
               {"movementNo":number,"vehicle":vehicle,"netMt":str(tonnes),
                "reason":"Confirmed 11-Oct Shift C under 21:00-05:00 mine operating day",
                "before":before,"after":{"status":"VALID","weighAt":stamp,"issue":w.issue},
                "originalWbSource":w.source_raw,"originalWbDestination":w.destination_raw})
        stats["corrected"]+=1
    db.flush()
    return {"corrected":stats["corrected"],"alreadyValid":stats["alreadyValid"],
            "skipped":skip,"confirmedBatch":batch.batch_id,
            "reviewRemainingInBatch":batch.review_rows}
