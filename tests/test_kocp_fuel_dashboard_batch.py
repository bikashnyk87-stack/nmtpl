"""KOCP HSD batch entry and fuel KPI regressions: no production writes."""
import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Equipment
from app.site_models import Site, SiteHsdTransaction, SiteTrip
from app.routers import site_ops

ROOT=Path(__file__).resolve().parents[1]
JS=ROOT/"app/static/simple_field_v1.js"


def test_add_ten_twenty_buttons_append_without_erasing_existing_rows():
    source=JS.read_text("utf-8")
    trip=source[source.index("function addSimpleTripRows(amount)"):source.index("function copyLookupDefault(")]
    hsd=source[source.index("function addSimpleHsdRows(amount)"):source.index("async function saveSimpleHsd(")]
    helper=source[source.index("function refreshEntryRowCounts()"):source.index("function addSimpleTripRows(amount)")]
    mock=r"""
const assert=require('node:assert/strict');
function rows(kind,count){return Array.from({length:count},(_,i)=>({dataset:{i:String(i)},querySelectorAll:()=>[]}))}
const tripRows=rows('TRIP',10),hsdRows=rows('HSD',10);
function box(store,selector){
 return {
  querySelectorAll:()=>store,
  insertAdjacentHTML:(placement,html)=>{
   assert.equal(placement,'beforeend');
   for(const match of html.matchAll(/data-i="(\d+)"/g))
    store.push({dataset:{i:match[1]},querySelectorAll:()=>[]});
  }
 }
}
const tripBody=box(tripRows,'.simple-trip-row'),hsdBody=box(hsdRows,'.simple-hsd-row');
const nodes={simpleTripRows:tripBody,simpleHsdRows:hsdBody,stRowCount:{textContent:''},shRowCount:{textContent:''},stRows:{value:'10',dataset:{}},shRows:{value:'10',dataset:{}}};
const $=id=>nodes[id],toast=()=>{},bindLookups=()=>{},saveDraft=()=>{},draftKey=()=> 'TRIP',hsdDraftKey=()=> 'HSD_ISSUE_V2',state={module:'TRIP'};
function tripGridRows(kind,count,start){return Array.from({length:count},(_,i)=>'<tr data-i="'+(start+i)+'"></tr>').join('')}
function hsdGridRows(count,start){return Array.from({length:count},(_,i)=>'<tr data-i="'+(start+i)+'"></tr>').join('')}
addSimpleTripRows(10);
assert.equal(tripRows.length,20);
addSimpleTripRows(20);
assert.equal(tripRows.length,40);
assert.equal(tripRows[0].dataset.i,'0');
assert.equal(tripRows[39].dataset.i,'39');
addSimpleHsdRows(10);
assert.equal(hsdRows.length,20);
addSimpleHsdRows(20);
assert.equal(hsdRows.length,40);
assert.equal(hsdRows[0].dataset.i,'0');
assert.equal(hsdRows[39].dataset.i,'39');
assert.equal(nodes.stRowCount.textContent,'40 rows');
assert.equal(nodes.shRowCount.textContent,'40 rows');
console.log('Trip + HSD buttons append 10/20 without dropping previously entered rows');
"""
    proc=subprocess.run(["node","-e",helper+trip+hsd+"\n"+mock],capture_output=True,text=True,timeout=20)
    assert proc.returncode==0,proc.stdout+"\n"+proc.stderr


def test_hsd_modes_drafts_globals_and_stock_label():
    js=JS.read_text("utf-8")
    html=(ROOT/"app/static/site.html").read_text("utf-8")
    assert "Object.assign(window,{saveTiomSimpleProduction,clearTiomSimpleDraft,addSimpleTripRows,rebuildSimpleTripRows,setSimpleHsdMode,openHsdOpening,saveHsdOpening,addSimpleHsdRows" in js
    assert "hsdDraftKey()" in js
    assert "draftKey('HSD_'+activeHsdEntryType+'_V2')" in js
    assert "Recover Previous Draft" in js
    assert "Fuel Issues" in js and "Fuel Receipts" in js
    assert "stockBalance" not in js[js.index("function fuelKpiCards"):js.index("function fuelAssetBreakdown")]
    assert "NOT closing stock" in js
    assert "sourceRecordUid:uid.value" in js
    assert "simple_field_v1.js?v=kocp-opening-colour-r7" in html
    proc=subprocess.run(["node","--check",str(JS)],capture_output=True,text=True,timeout=20)
    assert proc.returncode==0,proc.stderr


def test_read_only_fuel_summary_separates_receipts_issues_and_opening(monkeypatch):
    engine=create_engine("sqlite://",poolclass=StaticPool,connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    operating_day=date(2026,10,31)
    monkeypatch.setattr(site_ops,"get_user",lambda db,request:SimpleNamespace(admin=True))
    monkeypatch.setattr(site_ops,"require_site",lambda db,user,site_id:site_id)
    monkeypatch.setattr(site_ops,"resolve_site_context",lambda db,site_id:SimpleNamespace(operating_date=operating_day))
    with Session(engine) as db:
        db.add(Site(site_id="KOCP",site_name="KOCP",short_name="KOCP",active=True))
        db.add(Equipment(machine_id="T001",door_no="42",vehicle_no="OD-05CK-6249",type="EICHER TIPPER",group="KOCP",ownership="NMTPL",active=True))
        for i,(day,kind,litres) in enumerate([
            (date(2026,10,30),"ISSUE",20),
            (operating_day,"ISSUE",5),
            (operating_day,"RECEIPT",40),
            (operating_day,"OPENING",100),
        ],1):
            db.add(SiteHsdTransaction(
                transaction_id=f"HSD-TEST-{i}",site_id="KOCP",operating_date=day,
                shift="A",transaction_type=kind,asset_id="T001" if kind=="ISSUE" else None,
                litres=litres,source_type="TEST",source_record_uid=str(i),
                entered_by="tester",status="POSTED"))
        db.add(SiteTrip(trip_id="TEST-1",site_id="KOCP",operating_date=operating_day,
                        shift="A",quantity_mt=100,quantity_cum=250,
                        vehicle_id="T001",entered_by="tester",status="POSTED"))
        db.commit()
        before=db.scalar(select(func.count()).select_from(SiteHsdTransaction))
        output=site_ops.fuel_summary("KOCP",object(),date(2026,10,1),operating_day,db)
        assert output["periodTotals"]["receiptL"]==40
        assert output["periodTotals"]["issueL"]==25
        assert output["periodTotals"]["netMovementL"]==15
        assert output["periodTotals"]["receiptCount"]==1
        assert output["periodTotals"]["issueCount"]==2
        assert output["todayTotals"]["issueL"]==5
        assert output["litresPerMt"]==0.25
        assert output["litresPerCum"]==0.1
        assert output["stockBalance"] is None
        assert "Door 42" in output["issueByAsset"][0]["label"]
        assert db.scalar(select(func.count()).select_from(SiteHsdTransaction))==before
    engine.dispose()


def test_kocp_dashboard_has_fuel_panel_and_old_kpis_preserved():
    js=JS.read_text("utf-8")
    assert "Fuel / HSD — Operating Summary" in js
    assert "Top Diesel-Using Equipment" in js
    assert "Fuel / Coal MT" in js
    assert "Fuel / OB CuM" in js
    assert "HSD Issued" in js
