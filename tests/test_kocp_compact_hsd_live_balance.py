"""Regression tests for KOCP compact receipts and live posted fuel stock."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import subprocess

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.site_models import Site, SiteHsdTransaction
from app.routers import site_ops

ROOT=Path(__file__).resolve().parents[1]
JS=ROOT/"app/static/simple_field_v1.js"


def test_receipt_posts_one_transaction_and_refreshes_live_stock():
    src=JS.read_text("utf8")
    balance=src[src.index("function hsdBalanceStrip("):src.index("function fuelKpiCards(")]
    receipt=src[src.index("function clearCompactHsdReceipt("):src.index("function toggleHsdRow(")]
    harness=r"""
const assert=require('node:assert/strict');
const el={
 rcSave:{disabled:false,isConnected:true},rcDate:{value:'2026-10-31'},
 rcShift:{value:'B'},rcSupplier:{value:'  Fuel Supplier Ltd  ',focus:()=>{}},
 rcLitres:{value:'120.250'},rcReference:{value:'CH-1002'},rcUid:{value:''},
 rcSaveStatus:{textContent:'',className:''},hsdBalanceLitres:{textContent:'Old'},
 hsdBalanceNote:{textContent:'Old'},hsdTodayReceived:{textContent:'0 L'},
 hsdTodayIssued:{textContent:'0 L'}
};
const classes=new Set();
const strip={classList:{toggle:(k,v)=>v?classes.add(k):classes.delete(k),
 remove:k=>classes.delete(k),add:k=>classes.add(k)}};
const document={querySelector:q=>q==='.hsd-balance-strip'?strip:null};
const $=id=>el[id],state={ctx:{operatingDate:'2026-10-31'}},siteId='KOCP';
const dashNum=(n,p)=>Number(n).toFixed(p),esc=x=>String(x);
const storage=new Map(),localStorage={removeItem:k=>storage.delete(k),
 setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k)};
const hsdReceiptDraftKey=()=> 'RECEIPT_DRAFT';
const saveDraft=()=>storage.set('RECEIPT_DRAFT',el.rcUid.value);
let posts=0,gets=0,renders=0;
const api=async(url,opt)=>{
 if(url.endsWith('/hsd')&&opt?.method==='POST'){
   let p=JSON.parse(opt.body);
   assert.equal(p.transactionType,'RECEIPT');
   assert.equal(p.supplier,'Fuel Supplier Ltd');
   assert.equal(p.litres,'120.250');
   assert.equal(p.referenceNo,'CH-1002');
   assert.ok(p.sourceRecordUid);
   posts++;return {ok:true};
 }
 if(url.includes('/fuel/balance?')){
   gets++;return {stockBalance:990.5,todayReceiptL:120.25,
     todayIssueL:5,stockNote:'Calculated posted stock.'};
 }
 throw Error('Unexpected URL '+url);
};
const toast=()=>{},render=async()=>{renders++};
(async()=>{
 await saveCompactHsdReceipt();
 assert.equal(posts,1);
 assert.equal(gets,1,'Must fetch posted balance from Neon after receipt');
 assert.equal(el.hsdBalanceLitres.textContent,'990.50 L');
 assert.equal(el.hsdTodayReceived.textContent,'120.25 L');
 assert.equal(el.hsdTodayIssued.textContent,'5.00 L');
 assert.equal(el.rcSupplier.value,'');
 assert.equal(el.rcLitres.value,'');
 assert.equal(el.rcUid.value,'');
 assert.equal(storage.has('RECEIPT_DRAFT'),false);
 assert.equal(renders,1);
 assert.equal(classes.has('hsd-balance-ready'),true);
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    p=subprocess.run(["node","-e",balance+"\n"+receipt+"\n"+harness],
        capture_output=True,text=True,timeout=20)
    assert p.returncode==0,p.stdout+"\n"+p.stderr


def test_balance_api_and_dashboard_share_true_posted_ledger(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(site_ops,"get_user",lambda db,request:SimpleNamespace(admin=True))
    monkeypatch.setattr(site_ops,"require_site",lambda db,actor,site_id:site_id)
    monkeypatch.setattr(site_ops,"resolve_site_context",
        lambda db,site_id:SimpleNamespace(operating_date=date(2026,10,31)))
    with Session(engine) as db:
        db.add(Site(site_id="KOCP",site_name="KOCP",short_name="KOCP",active=True))
        db.add(SiteHsdTransaction(transaction_id="R-1",site_id="KOCP",
            operating_date=date(2026,10,31),shift="B",transaction_type="RECEIPT",
            litres=Decimal("50"),status="POSTED",entered_by="tester"))
        db.commit()
        missing=site_ops.fuel_live_balance("KOCP",object(),date(2026,10,31),db)
        assert missing["stockBalance"] is None
        assert missing["todayReceiptL"]==50
        db.add(SiteHsdTransaction(transaction_id="O-1",site_id="KOCP",
            operating_date=date(2026,10,31),transaction_type="OPENING",
            reference_no="VERIFIED-STOCK",litres=Decimal("200"),
            status="POSTED",entered_by="tester"))
        db.add(SiteHsdTransaction(transaction_id="I-1",site_id="KOCP",
            operating_date=date(2026,10,31),shift="B",transaction_type="ISSUE",
            litres=Decimal("35"),status="POSTED",entered_by="tester"))
        db.commit()
        latest=site_ops.fuel_live_balance("KOCP",object(),date(2026,10,31),db)
        assert latest["stockBalance"]==215
        assert latest["todayReceiptL"]==50
        assert latest["todayIssueL"]==35
        summary=site_ops.fuel_summary("KOCP",object(),date(2026,10,1),date(2026,10,31),db)
        assert summary["stockBalance"]==latest["stockBalance"]
    engine.dispose()


def test_compact_receipt_layout_and_issue_post_refresh():
    js=JS.read_text("utf-8")
    begin=js.index("if(siteId==='KOCP'&&activeHsdEntryType==='RECEIPT')")
    end=js.index("  return simplePageHead(", js.index("panel('Recent Fuel Receipts'",begin))
    receipt=js[begin:end]
    assert "simpleHsdReceiptForm" in receipt
    for name in ("rcDate","rcShift","rcSupplier","rcLitres","rcReference"):
        assert name in receipt
    assert "Save Receipt" in receipt
    assert "addSimpleHsdRows" not in receipt and "shRows" not in receipt
    assert "hasPreviousReceiptDraft()" in receipt
    assert "hsdBalanceStrip(fuel)" in receipt
    issues=js[js.index("async function saveSimpleHsd("):js.index("function clearSimpleHsdDraft(")]
    assert "await refreshHsdBalance();" in issues
    assert "sourceRecordUid:uid.value" in js
    assert "simple_field_v1.js?v=kocp-compact-receipt-live-r8" in (ROOT/"app/static/site.html").read_text("utf-8")
    p=subprocess.run(["node","--check",str(JS)],capture_output=True,text=True,timeout=20)
    assert p.returncode==0,p.stderr
