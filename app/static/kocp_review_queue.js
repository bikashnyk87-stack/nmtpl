/* KOCP paper-card checker queue. Does not change source counts or posting rules. */
(function(){
"use strict";
const API="/api/KOCP/shift-register";
const s={items:[],total:0,more:false,selected:new Set(),dateOnly:false,kind:"ALL",opened:null,busy:false};
const get=id=>document.getElementById(id);
const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const enc=x=>encodeURIComponent(String(x));
const visible=()=>s.items.filter(x=>(!s.dateOnly||x.operatingDate===(get("srDate")?.value||get("opsTo")?.value))&&
 (s.kind==="ALL"||s.kind===x.kind));
function mount(){
 const parent=document.querySelector("#workspace .sr-workbench")||document.querySelector("#workspace .ops-dashboard");
 if(!parent)return false;
 if(get("kocpPendingQueue"))return true;
 const section=document.createElement("section");
 section.id="kocpPendingQueue";section.className="sr-card";
 section.innerHTML='<div class="sr-q-head"><div><h2>Pending MIS Verification <span id="srQCount"></span></h2>'+
 '<small>All pending dates · Coal and OB</small></div><button type="button" class="sr-small" onclick="KOCPQueue.refresh()">Refresh</button></div>'+
 '<div class="sr-q-filter"><label><input type="checkbox" id="srQDateOnly" onchange="KOCPQueue.date(this.checked)"> Selected date only</label>'+
 '<label>Type <select id="srQKind" onchange="KOCPQueue.kind(this.value)"><option value="ALL">Coal + OB</option>'+
 '<option value="COAL">Coal</option><option value="OB">OB</option></select></label></div>'+
 '<div id="srQList" aria-live="polite">Loading pending cards…</div>'+
 '<div class="sr-q-actions"><button id="srQVerify" type="button" class="sr-btn" onclick="KOCPQueue.verify()">Verify selected (0)</button><button id="srQVerifyAll" type="button" class="sr-small" onclick="KOCPQueue.verifyAll()">Verify all pending</button>'+
 '<span id="srQMessage" class="sr-muted">Compare with physical trip cards before verification.</span></div>';
 parent.appendChild(section);
 if(!get("kocpQueueStyle")){
  const st=document.createElement("style");st.id="kocpQueueStyle";
  st.textContent='.sr-q-head,.sr-q-filter,.sr-q-actions{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap}'+
  '.sr-q-head h2{margin:0 0 4px;font-size:16px}.sr-q-head small{color:#667d86}.sr-q-filter{justify-content:flex-start;padding:9px 0}'+
  '.sr-q-filter label{display:flex;align-items:center;gap:7px;font-size:12px}.sr-q-filter select{border:1px solid #ccdce1;border-radius:5px;padding:5px;background:white}'+
  '.sr-q-scroll{max-height:300px;overflow:auto;border:1px solid #dfe7eb;border-radius:7px}'+
  '.sr-q-table{width:100%;border-collapse:collapse;font-size:12px}.sr-q-table th{position:sticky;top:0;background:#eef5f6;z-index:2;text-align:left}'+
  '.sr-q-table th,.sr-q-table td{padding:8px;border-bottom:1px solid #e2e9ed;vertical-align:middle}'+
  '.sr-q-table td small{display:block;color:#667b87;margin-top:2px}.sr-q-table td:first-child{width:30px}'+
  '.sr-q-detail td{background:#f8fbfc;padding:10px}.sr-q-detail .sr-q-scroll{max-height:220px}'+
  '.sr-q-actions{justify-content:flex-start;margin-top:10px}.sr-q-actions button:disabled{opacity:.5;cursor:not-allowed}'+
  '.sr-q-empty{margin:12px 0;color:#536c78}.sr-q-note{font-size:12px;color:#4d6370;margin:7px 0}'+
  '@media(max-width:680px){.sr-q-scroll{overflow-x:auto}.sr-q-table{min-width:620px}}';
  document.head.appendChild(st);
 }
 return true;
}
function draw(){
 if(!mount())return;
 const rows=visible();
 get("srQCount").textContent="("+s.total+")";
 get("srQDateOnly").checked=s.dateOnly;get("srQKind").value=s.kind;
 const limited=s.more?'<p class="sr-error">More than 300 pending cards; oldest 300 shown. Bulk action is limited to the cards on screen.</p>':"";
 if(!rows.length)get("srQList").innerHTML=limited+'<p class="sr-q-empty">'+
 (s.total?"Nothing pending for this date/type. Untick Selected date only to see other days.":"No pending Coal or OB cards.")+'</p>';
 else get("srQList").innerHTML=limited+'<div class="sr-q-scroll"><table class="sr-q-table"><thead><tr>'+
 '<th><input id="srQAll" type="checkbox" title="Select all eligible cards" onchange="KOCPQueue.all(this.checked)"></th>'+
 '<th>Date / shift</th><th>Register / equipment</th><th>Material / driver</th><th>Trips</th><th>Verify</th></tr></thead><tbody>'+
 rows.map(x=>{
  const can=!!x.canVerify;
  return '<tr class="sr-q-card-row"><td><input type="checkbox" value="'+esc(x.cardId)+'" '+(s.selected.has(x.cardId)?"checked ":"")+
   (!can||s.busy?"disabled ":"")+'aria-label="Select '+esc(x.kind)+' '+esc(x.operatingDate)+'" onchange="KOCPQueue.select(this.value,this.checked)"></td>'+
   '<td><b>'+esc(x.operatingDate)+'</b><small>Shift '+esc(x.shift)+'</small></td>'+
   '<td><b>'+esc(x.kind)+'</b><small>'+esc(x.sourceRef||x.cardId)+'</small>'+
   '<small>Tipper '+esc(x.vehicleLabel||x.vehicleId||"—")+'</small></td>'+
   '<td>'+esc(x.materialName||x.materialId||"—")+'<small>Driver '+esc(x.driverName||x.driverId||"—")+'</small>'+
   '<small>Entered by '+esc(x.enteredBy)+'</small></td>'+
   '<td><b>'+Number(x.tripCount||0)+'</b><small>'+Number(x.rowCount||0)+' rows</small></td>'+
   '<td>'+(can?'<div class="sr-q-row-actions"><button type="button" class="sr-small sr-q-approve" onclick="KOCPQueue.verifyOne(\''+esc(x.cardId)+'\')">Verify</button>'+
   '<button type="button" class="sr-small" onclick="KOCPQueue.rejectOne(\''+esc(x.cardId)+'\')">Return</button></div>':
   '<small>Checker permission required</small>')+'</td></tr>'+
   '<tr class="sr-q-detail"><td colspan="6">'+detailHtml(x)+'</td></tr>';
 }).join("")+'</tbody></table></div>';
 update();
}
function detailHtml(card){
 const isOb=card.kind==="OB";
 const pairs=[
  ['Source ref',card.sourceRef||card.cardId],['Material',card.materialName||card.materialId],
  ['Tipper',card.vehicleLabel||card.vehicleId],['Driver',card.driverName||card.driverId],
  ['Paper trips',card.declaredTotal??"Not stated"],['Entered by',card.enteredBy]
 ];
 if(card.routeId)pairs.push(['Default route',card.routeName||card.routeId]);
 if(card.relayCode)pairs.push(['Relay',card.relayCode]);
 if(card.openingHmr!==''||card.closingHmr!=='')pairs.push(['HMR',String(card.openingHmr||"—")+' → '+String(card.closingHmr||"—")]);
 if(card.openingKmr!==''||card.closingKmr!=='')pairs.push(['KMR',String(card.openingKmr||"—")+' → '+String(card.closingKmr||"—")]);
 const head='<div class="sr-q-meta">'+pairs.map(([name,value])=>
  '<span><b>'+esc(name)+':</b> '+esc(value||"—")+'</span>').join("")+'</div>';
 const body=(card.lines||[]).map(l=>'<tr><td>'+esc(l.lineNo)+'</td>'+
 '<td>'+esc(isOb?(l.excavatorLabel||l.excavatorId):(l.vehicleLabel||l.vehicleId))+'</td>'+
 '<td>'+esc(isOb?(l.patchLabel||l.patchCode||l.sourceLocationName||l.sourceLocationId):(l.driverName||l.driverId))+'</td>'+
 '<td>'+esc(isOb?(l.pointLabel||l.pointCode||l.destinationLocationName||l.destinationLocationId):"—")+'</td>'+
 '<td>'+esc(l.routeName||l.routeId||card.routeName||card.routeId||"—")+'</td><td><b>'+Number(l.tripCount||0)+'</b></td></tr>').join("");
 return head+'<div class="sr-q-line-scroll"><table class="sr-q-line-table"><thead><tr><th>#</th><th>'+
 (isOb?"Excavator":"Vehicle")+'</th><th>'+(isOb?"Patch":"Driver")+
 '</th><th>Unloading point</th><th>Route / lead</th><th>Trips</th></tr></thead>'+
 '<tbody>'+body+'</tbody></table></div>';
}
function update(){
 const eligible=visible().filter(x=>x.canVerify),selected=eligible.filter(x=>s.selected.has(x.cardId));
 const button=get("srQVerify"),all=get("srQAll");
 button.disabled=s.busy||!selected.length;
 button.textContent=s.busy?"Verifying…":"Verify selected ("+selected.length+")";
 const allButton=get("srQVerifyAll");if(allButton){allButton.disabled=s.busy||!eligible.length;allButton.textContent=s.more?"Verify all shown ("+eligible.length+")":"Verify all pending ("+eligible.length+")";}
 if(all){all.checked=eligible.length>0&&eligible.every(x=>s.selected.has(x.cardId));
 all.indeterminate=!all.checked&&eligible.some(x=>s.selected.has(x.cardId));}
}
function select(id,checked){if(checked)s.selected.add(id);else s.selected.delete(id);update()}
function all(checked){visible().filter(x=>x.canVerify).forEach(x=>checked?s.selected.add(x.cardId):s.selected.delete(x.cardId));draw()}
function date(flag){s.dateOnly=flag;s.opened=null;draw()}
function kind(v){s.kind=["COAL","OB"].includes(v)?v:"ALL";s.opened=null;draw()}
function detail(id){s.opened=s.opened===id?null:id;draw()}
async function refresh(){
 if(!mount())return;
 try{
  const data=await api(API+"/review-queue");
  s.items=data.items||[];s.total=Number(data.totalPending||0);s.more=!!data.hasMore;s.opened=null;
  const ids=new Set(s.items.filter(x=>x.canVerify).map(x=>x.cardId));
  for(const id of s.selected)if(!ids.has(id))s.selected.delete(id);
  draw();
 }catch(e){const area=get("srQList");if(area)area.textContent="Could not load pending records: "+e.message;}
}
async function verifyCards(cards){
 if(s.busy||!cards.length)return;
 const trips=cards.reduce((v,x)=>v+Number(x.tripCount||0),0);
 if(!confirm("Have you checked these "+cards.length+" physical paper card(s), totalling "+trips+
 " trips? Confirm to verify and post them to KOCP production."))return;
 s.busy=true;draw();
 let approved=0,posted=0;const errors=[];
 for(const card of cards){
  try{
   const current=await api(API+"/cards/"+enc(card.cardId));
   if(current.status!=="SUBMITTED"||current.version!==card.version||Number(current.tripCount)!==Number(card.tripCount))
    throw Error("Record changed. Refresh and review it again.");
   await api(API+"/cards/"+enc(card.cardId)+"/decision",{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({action:"VERIFY",expectedVersion:current.version})
   });
   approved++;posted+=Number(card.tripCount||0);s.selected.delete(card.cardId);
  }catch(e){errors.push(card.operatingDate+" "+card.kind+" "+(card.sourceRef||card.cardId.slice(-8))+": "+e.message)}
 }
 s.busy=false;
 await refresh();
 await window.KOCPSR?.history?.();
 const msg=get("srQMessage");
 if(msg){msg.textContent=approved+" verified ("+posted+" trips posted)."+
  (errors.length?" "+errors.length+" not verified: "+errors.join("; "):"");
  msg.className=errors.length?"sr-error":"sr-success";}
}
async function verify(){return verifyCards(visible().filter(x=>x.canVerify&&s.selected.has(x.cardId)))}
async function verifyAll(){return verifyCards(visible().filter(x=>x.canVerify))}
async function verifyOne(id){const card=s.items.find(x=>x.cardId===id&&x.canVerify);if(card)return verifyCards([card])}
async function rejectOne(id){
 if(s.busy)return;
 const card=s.items.find(x=>x.cardId===id&&x.canVerify);
 if(!card)return;
 const reason=prompt("Reason to return this paper card for correction (minimum 5 characters):");
 if(!reason||reason.trim().length<5)return;
 try{
  const current=await api(API+"/cards/"+enc(card.cardId));
  if(current.status!=="SUBMITTED"||current.version!==card.version)throw Error("Card changed; refresh before returning.");
  await api(API+"/cards/"+enc(id)+"/decision",{method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify({action:"REJECT",expectedVersion:current.version,reason:reason.trim()})});
  await refresh();await window.KOCPSR?.history?.();
  get("srQMessage").textContent="Card returned for correction.";
 }catch(e){const msg=get("srQMessage");if(msg){msg.textContent=e.message;msg.className="sr-error";}}
}
window.KOCPQueue={mount,refresh,draw,select,all,date,kind,detail,verify,verifyAll,verifyOne,rejectOne};
})();
