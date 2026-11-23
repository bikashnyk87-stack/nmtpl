// Regression test for TTIO: truck-specific WB rows and restored local drafts.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const js=fs.readFileSync('app/static/tiom_phase1.js','utf8');

const start=js.indexOf('  window.loadTiomWbSuggestions=function(autoFill){');
const stop=js.indexOf('  window.copyPreviousMisRow=',start);
assert(start>0&&stop>start,'WB loader must be present');
const loader=js.slice(start,stop);

function setup({vehicle='DT-10',rows=[],misReportId='',date='2026-11-22',shift='A'}={}){
  let currentRows=rows.map(x=>({...x})), renders=0,saves=0;
  const values={tm_vehicle:vehicle,tm_date:date,tm_shift:shift};
  const state={textContent:''},req=[];
  const T={misReportId,misRows:15,mis:{products:[]},wbSuggestions:[]};
  const ctx={window:{},T,q:id=>id==='tm_wb_state'?state:null,v:id=>values[id]||'',
    appRun:(ok,err)=>({getTiomWbSuggestions(args){req.push({args,ok,err});}}),
    collectTripRows:()=>currentRows.map(x=>({...x})),
    renderMisRows:r=>{renders++;currentRows=r.map(x=>({...x}));},
    tripSourceChanged:()=>{},
    // Linked preview is tested end-to-end in tiom_mis_linked_wb_preview.cjs.
    renderMisLinkedWb:()=>{},
    draftSave:()=>{saves++;},
  };
  vm.runInNewContext(loader,ctx,{timeout:1000});
  return {T,values,state,req,run:auto=>ctx.window.loadTiomWbSuggestions(auto),
    get rows(){return currentRows;},get renders(){return renders;},get saves(){return saves;}};
}
const wb=(id,material='Fines')=>({wbMovementKey:id,materialId:material,sourceLocationId:'PA',destinationLocationId:'S16',qtyMt:40});
const sourceRow=(id,material='Waste Rock')=>({movementKey:id,movementNo:id,
  materialId:material,sourceLocationId:'PIT',destinationLocationId:'DUMP',netMt:37.2});
const stale=Array.from({length:8},(_,i)=>wb('OTHER-'+i));
const manual={materialId:'ROM',sourceLocationId:'PIT',machineId:'LOADER-1'};

// 5 already linked, 220 other trucks: zero eligible. Eight stale WB rows
// from the local draft must not appear on the DT-10 MIS form.
const one=setup({rows:[...stale,manual]});
one.run(true);
assert.equal(one.req.length,1);
assert.equal(one.req[0].args.vehicleId,'DT-10');
one.req[0].ok({rows:[],message:'0 available; 5 already linked to another MIS report; 220 WB movements belong to other vehicles.'});
assert.equal(one.rows.filter(r=>r.wbMovementKey).length,0);
assert.equal(one.rows.filter(r=>r.materialId==='ROM').length,1);
assert.match(one.state.textContent,/Removed 8 stale or already-linked WB row/);
assert.match(one.state.textContent,/5 already linked/);
assert.equal(one.renders,1);
assert.equal(one.saves,1);

// Autoload after switching must populate only exact current-truck eligible
// WB keys, not merge an unrelated prior vehicle's draft rows.
const two=setup({rows:[...stale,manual]});
two.run(true);
two.req[0].ok({rows:[sourceRow('DT10-1'),sourceRow('DT10-2')],message:'2 available'});
assert.deepEqual(Array.from(two.rows.filter(x=>x.wbMovementKey),x=>x.wbMovementKey),['DT10-1','DT10-2']);
assert.equal(two.rows.filter(x=>x.materialId==='ROM').length,1);

// When the user changes vehicle before the first HTTP response, stale async
// results must never place another vehicle's suggestions into the grid.
const three=setup({vehicle:'DT-09'});
three.run(true);
three.values.tm_vehicle='DT-10';
three.run(true);
three.req[1].ok({rows:[sourceRow('DT10-1')],message:'1 available'});
three.req[0].ok({rows:[sourceRow('DT09-1')],message:'1 available'});
assert.deepEqual(Array.from(three.rows.filter(x=>x.wbMovementKey),x=>x.wbMovementKey),['DT10-1']);

// Restored drafts must be validated on explicit load even when no automatic
// additions are requested.
const four=setup({rows:[wb('OTHER-DRAFT')]});
four.run(false);
four.req[0].ok({rows:[],message:'0 available'});
assert.equal(four.rows.filter(x=>x.wbMovementKey).length,0);
assert.equal(four.saves,1);

// Missing confirmed WB is a sync state, not a reason to delete previously
// entered WB references from the current browser form.
const pending=setup({rows:[wb('PREVIOUSLY-CONFIRMED'),manual]});
pending.run(true);
pending.req[0].ok({rows:[],linkedRows:[],batch:null,
  state:'AWAITING_WB_CONFIRMATION',message:'WB confirmation pending'});
assert.equal(pending.rows.filter(x=>x.wbMovementKey).length,1);
assert.equal(pending.saves,0);
assert.match(pending.state.textContent,/not been cleared/);

// Vehicle switch immediately removes old truck's WB badges (manual entries
// are retained), without waiting for the network.
const a=js.indexOf('  window.misVehicleChanged=function(){'),b=js.indexOf('  function factorForMaterial',a);
assert(a>=0&&b>a,'Vehicle change handler is present');
const vars={tm_vehicle:'DT-10',tm_wb_state:''};
let changedRows=[...stale,manual], lookup=0;
const vmctx={window:{},T:{lastVehicleId:'DT-09',mis:{vehicles:[]},misRows:15},
  v:id=>vars[id]||'',q:id=>id==='tm_wb_state'?{set textContent(v){vars.tm_wb_state=v;}}:null,
  collectTripRows:()=>changedRows,renderMisRows:r=>{changedRows=r;},
  wireDriverMeterCalc:()=>{},draftSave:()=>{},loadTiomWbSuggestions:()=>lookup++,
};
vm.runInNewContext(js.slice(a,b),vmctx,{timeout:1000});
vmctx.window.misVehicleChanged();
assert.equal(changedRows.filter(r=>r.wbMovementKey).length,0);
assert.equal(changedRows.filter(r=>r.materialId==='ROM').length,1);
assert.equal(lookup,1);

assert.match(js,/if\(collectTripRows\(\)\.some\(r=>r\.wbMovementKey\)\)loadTiomWbSuggestions\(false\)/);
console.log('5 MIS WB vehicle isolation cases passed');
