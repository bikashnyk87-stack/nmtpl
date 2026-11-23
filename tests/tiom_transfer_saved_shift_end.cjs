// Run the real transfer UI handlers in isolation against a saved backend response.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const src = fs.readFileSync('app/static/tiom_phase1.js','utf8');
const start = src.indexOf('  window.openMachineTransfer=function(){');
const stop = src.indexOf('  window.cancelMachineTransfer=function',start);
assert(start>=0 && stop>start);
const handlers=src.slice(start,stop);

function runWith(result){
  const panel = {hidden:true,dataset:{},innerHTML:'',scrollIntoView(){}};
  const values={tm_date:'2026-11-22',tm_shift:'A',tm_transfer_choice:'dep-1'};
  const T={transferRows:[],transferLocations:[]};
  const msgs=[], calls=[];
  const ctx={
    window:{},T,
    q:id=>id==='tm_transfer_panel'?panel:null,
    v:id=>values[id]||'',
    safe:value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;'),
    opts:rows=>'<option value="">-- Select --</option>'+rows.map(x=>'<option value="'+x.id+'">'+x.label+'</option>').join(''),
    toast:(msg,isError)=>msgs.push({msg,isError}),
    appRun:(success,failure)=>({
      getTiomTransferOptions(args){calls.push(args);success(result)},
    }),
  };
  vm.runInNewContext(handlers,ctx,{timeout:1000});
  ctx.window.openMachineTransfer();
  return {panel,T,msgs,calls,window:ctx.window,values};
}

const saved={
  date:'2026-11-22',shift:'A',savedCount:10,closedCount:0,
  rows:[{deploymentId:'dep-1',machineId:'ZAXIS670-01',machineLabel:'ZAXIS 670-01',
         sourceLocationId:'PIT1',sourceLabel:'PIT1 / RL 720',fromTime:'06:00',toTime:'14:00'}],
  locations:[{id:'PIT1',label:'PIT1'},{id:'MSP4',label:'MSP4'}],
};
const done=runWith(saved);
assert.equal(done.calls.length,1);
assert.equal(done.calls[0].date,'2026-11-22');
assert.equal(done.calls[0].shift,'A');
assert.equal(done.msgs.length,0,'saved machine must not trigger false empty error');
assert.match(done.panel.innerHTML,/ZAXIS 670-01/);
assert.match(done.panel.innerHTML,/dep-1/);
assert.match(done.panel.innerHTML,/PIT1 \/ RL 720/);
done.window.chooseMachineTransfer();
assert.equal(done.panel.dataset.deploymentId,'dep-1');
assert.match(done.panel.innerHTML,/tm_transfer_end/);
assert.match(done.panel.innerHTML,/tm_transfer_start/);
assert.match(done.panel.innerHTML,/MSP4/);

const none=runWith({rows:[],savedCount:10,closedCount:10,locations:[]});
assert.match(none.panel.innerHTML,/Found 10 saved assignment/);
assert.doesNotMatch(none.panel.innerHTML,/Save Machine Setup first/);

const fresh=runWith({rows:[],savedCount:0,closedCount:0,locations:[]});
assert.match(fresh.panel.innerHTML,/Save Machine Setup first/);
console.log('3 transfer UI states passed: saved shift-end, all closed, none saved');
