"""KOCP: prove that typing part of a registration and pressing Tab selects the real asset.

Runs the production JS picker logic in Node with a minimal DOM double. This
guards against accidentally storing just the search text without the machine ID.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app/static/simple_field_v1.js"


def test_unique_vehicle_tab_commits_full_registration_and_machine_id():
    src=UI.read_text("utf-8")
    start=src.index("function resolveLookupChoice(")
    end=src.index("document.addEventListener('click',e=>{document.querySelectorAll('.lookup.open')",start)
    logic=src[start:end]
    harness=r"""
const assert=require('node:assert/strict');
const events={};
const classes=new Set();
const input={
 value:'',dataset:{},tabIndex:0,
 addEventListener:(t,fn)=>{events[t]=fn},
 setAttribute:()=>{},removeAttribute:()=>{},
 dispatchEvent:(evt)=>{events[evt.type]?.(evt)},
 getClientRects:()=>[{}],
 focus:()=>{},
 select:()=>{}
};
const hidden={value:''};
const menu={
 innerHTML:'',
 querySelectorAll:()=>[],
 querySelector:()=>null,
 insertAdjacentHTML:()=>{}
};
const wrap={
 dataset:{kind:'ASSET',groups:''},classList:{
  add:t=>classes.add(t),remove:t=>classes.delete(t),
  toggle:(t,ok)=>ok?classes.add(t):classes.delete(t),
  contains:t=>classes.has(t)
 },
 querySelector:(q)=>q==='input[type=text]'?input:q==='input[type=hidden]'?hidden:menu
};
const next={tabIndex:0,getClientRects:()=>[{}],focus:()=>{next.focused=true}};
const root={querySelectorAll:()=>[wrap]};
const document={querySelectorAll:()=>[input,next]};
const siteId='KOCP',state={module:'HSD'},esc=x=>x,
 itemAllowed=(w,x)=>true;
let data=[{id:'127',vehicleNo:'OD-05CK-6249',doorNo:'',
  rentalRef:'',label:'ID 127 · OD-05CK-6249',group:'KOCP',sub:'BOLERO CAMPOR'}];
const api=async()=>data;
bindLookups(root);
(async()=>{
 input.value='6249';
 events.input();
 let wasPrevented=false;
 await events.keydown({key:'Tab',shiftKey:false,
   preventDefault:()=>{wasPrevented=true}});
 assert.equal(hidden.value,'127','Asset ID must be selected, not raw text');
 assert.equal(input.value,'ID 127 · OD-05CK-6249');
 assert.equal(input.dataset.vehicleNo,'OD-05CK-6249');
 assert.equal(next.focused,true,'Tab moves to Litres after selection');
 assert.equal(wasPrevented,true,'pending async lookup uses explicit focus');
 // Two matching registrations must NOT silently choose an arbitrary vehicle.
 hidden.value='';input.value='624';next.focused=false;
 data=[{id:'127',vehicleNo:'OD-05CK-6249',label:'ID 127 · OD-05CK-6249'},
       {id:'128',vehicleNo:'OD-03S-6240',label:'ID 128 · OD-03S-6240'}];
 events.input();
 await events.keydown({key:'Tab',shiftKey:false,preventDefault:()=>{}});
 assert.equal(hidden.value,'','Ambiguous selection must remain uncommitted');
 assert.equal(classes.has('lookup-unresolved'),true);
 // Exact typed registration is safe even when another match is present.
 const exact=resolveLookupChoice(data,'OD-05CK-6249');
 assert.equal(exact.id,'127');
 assert.equal(resolveLookupChoice(data,'624'),null);
 assert.equal(resolveLookupChoice(data,'',0).id,'127');
 console.log('KOCP Tab selection, ambiguous safety and exact match OK');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    proc=subprocess.run(["node","-e",logic+"\n"+harness],
                        cwd=ROOT,capture_output=True,text=True,timeout=20)
    assert proc.returncode==0, proc.stdout+"\n"+proc.stderr


def test_accessibility_and_hsd_guardrails():
    src=UI.read_text("utf-8")
    html=(ROOT/"app/static/site.html").read_text("utf-8")
    css=(ROOT/"app/static/simple_field_v1.css").read_text("utf-8")
    assert 'role="combobox"' in src and 'role="listbox"' in src
    assert 'aria-expanded' in src and 'aria-selected' in src
    assert "if(!Number.isFinite(Number(litres))||Number(litres)<=0)" in src
    assert "lookup-unresolved" in src
    assert ".lookup-help" in css
    assert "simple_field_v1.js?v=kocp-compact-receipt-live-r8" in html
