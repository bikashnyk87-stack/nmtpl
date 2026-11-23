// TIOM linked-WB visibility: five already-linked records remain viewable,
 // but must never be inserted into a new unsaved MIS report.
const fs=require('node:fs'),assert=require('node:assert/strict'),vm=require('node:vm');
const js=fs.readFileSync('app/static/tiom_phase1.js','utf8');
const api=fs.readFileSync('app/routers/webapp.py','utf8');
const start=js.indexOf('  function renderMisLinkedWb(rows){');
const end=js.indexOf('  window.copyPreviousMisRow=',start);
assert(start>=0&&end>start);
const runCode=js.slice(start,end);
const linkedRows=Array.from({length:5},(_,i)=>({
  movementNo:'20264014144'+String(100+i),material:'Waste Rock Thakurani',
  netMt:[35.22,36.22,37.64,40.58,38.8][i],
  reportId:'fdfd3648-2233-49be-a41a-8dc13bff1391',
  reportStatus:'SUBMITTED',linkState:'SAVED_REPORT',
}));
function run(data){
 const elements={tm_wb_linked:{innerHTML:''},tm_wb_state:{textContent:''}};
 const vals={tm_vehicle:'DT-10',tm_date:'2026-11-22',tm_shift:'A'};
 const T={wbSuggestions:[],mis:{products:[]},misRows:15,misReportId:''};
 let rows=[],loaded=[],saved=0,requested=[];
 const context={window:{},T,
   q:id=>elements[id]||null,v:id=>vals[id]||'',
   n:(n,p)=>Number(n).toFixed(p??2),
   safe:x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
   draftSave:()=>{saved++},loadMisReport:id=>{loaded.push(id)},
   appRun:(ok,err)=>({getTiomWbSuggestions:p=>{requested.push(p);ok(data)}}),
   collectTripRows:()=>rows,renderMisRows:r=>{rows=r},tripSourceChanged:()=>{},
 };
 vm.runInNewContext(runCode,context,{timeout:1000});
 context.window.loadTiomWbSuggestions(true);
 return {elements,rows,T,loaded,requested,saved,context};
}
const d={rows:[],linkedRows,diagnostics:{available:0,alreadyLinked:5,otherVehicle:220},
 message:'0 available; 5 already linked to another MIS report; 220 WB movements belong to other vehicles.'};
const x=run(d);
assert.equal(x.requested[0].vehicleId,'DT-10');
assert.equal(x.rows.length,0,'existing linked WB may not be auto-inserted');
assert.match(x.elements.tm_wb_linked.innerHTML,/5 WB movement\(s\) already linked/);
assert.equal((x.elements.tm_wb_linked.innerHTML.match(/<tr>/g)||[]).length,6);
assert.equal((x.elements.tm_wb_linked.innerHTML.match(/Open report/g)||[]).length,5);
assert.ok(x.elements.tm_wb_linked.innerHTML.includes('35.22'));
assert.ok(x.elements.tm_wb_linked.innerHTML.includes('40.58'));
assert.equal(linkedRows.reduce((sum,r)=>sum+r.netMt,0).toFixed(2),'188.46');
assert.match(x.elements.tm_wb_state.textContent,/0 available; 5 already linked/);
x.context.window.openLinkedWbReport(linkedRows[0].reportId);
assert.equal(x.loaded[0],linkedRows[0].reportId);
assert.equal(x.saved,1,'preserve unsaved draft before viewing existing MIS');

const y=run({rows:[],linkedRows:[{...linkedRows[0],reportId:'',linkState:'CHECK_LINK'}],
 message:'0 available; 1 already linked'});
assert.match(y.elements.tm_wb_linked.innerHTML,/Check linked report/);
assert.doesNotMatch(y.elements.tm_wb_linked.innerHTML,/Open report/);
assert.equal(y.rows.length,0);
const z=run({rows:[],linkedRows:[],message:'0 available'});
assert.equal(z.elements.tm_wb_linked.innerHTML,'');

const section=api.split('def get_tiom_wb_suggestions(',2)[1].split('\ndef get_tiom_mis_report(',1)[0];
assert.match(section,/linked_rows\.append/);
assert.match(section,/other_linked\+=1/);
assert.match(section,/if rec and rec\.row_id not in own_row_ids/);
assert.match(section,/owner_report\.vehicle_id==vehicle\.machine_id/);
assert.match(section,/owner_report\.operating_date==day and owner_report\.shift==sh/);
assert.match(section,/'rows':out,'linkedRows':linked_rows/);
console.log('TIOM read-only linked WB preview: 3 visibility states and report navigation passed');
