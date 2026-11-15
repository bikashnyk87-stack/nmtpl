/* KOCP Shift MIS Register — paper-first Coal (aggregate) and OB (individual).
   No photos, no per-trip times; all operational options are supplied by Masters.
*/
(function(){
"use strict";
const PREFIX="/api/KOCP/shift-register";
const model={kind:"COAL",card:null,clientKey:null,lines:[],masters:{COAL:[],OB:[],codes:[],vehicles:[],excavators:[],materials:[],locations:[]},people:{}};
function enc(v){return encodeURIComponent(String(v||""))}
function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function newKey(){return (window.crypto?.randomUUID?.()||String(Date.now())+"-"+Math.random()).slice(0,120)}
function opts(items,value,placeholder="Choose from Masters"){
 return '<option value="">'+esc(placeholder)+'</option>'+items.map(x=>
 '<option value="'+esc(x.id||x.routeId||x.code)+'" '+((x.id||x.routeId||x.code)===value?'selected':'')+'>'+esc(x.label||x.name||x.title||x.code)+'</option>').join('');
}
function codeOptions(kind,value){return opts(model.masters.codes.filter(x=>x.kind===kind&&x.active).map(x=>({id:x.code,label:x.code+" — "+x.name})),value,"Select "+kind+" master")}
function vehicleOptions(activity,value){return opts(activity==="COAL"?model.masters.vehicles:model.masters.vehiclesOb,value,"Select tipper / door number")}
function routeOptions(kind,value){return opts(model.masters[kind].filter(x=>x.active).map(r=>({
id:r.routeId,label:r.group+" → "+r.destination+" | "+r.category+" | "+r.distanceRange
})),value,"Select approved route / lead")}
function materialOptions(kind,value){return opts(model.masters.materials.filter(x=>
 kind==="OB"?["CUM","M3","M³"].includes(String(x.unit||"").toUpperCase()):
 String(x.unit||"").toUpperCase()==="MT"),value,"Select "+kind+" material")}
function paperInput(id,value,label,type="text",attrs=""){return '<label class="sr-field"><span>'+esc(label)+'</span><input id="'+id+'" type="'+type+'" value="'+esc(value||"")+'" '+attrs+'></label>'}
function selectBox(id,label,html){return '<label class="sr-field"><span>'+esc(label)+'</span><select id="'+id+'">'+html+'</select></label>'}
function personInput(id,value){return '<input id="'+id+'" data-employee-id="'+esc(value||"")+'" value="'+esc(value||"")+
 '" list="'+id+'-list" autocomplete="off" placeholder="Search driver name / code" '+
 'oninput="KOCPSR.personSearch(this)" onchange="KOCPSR.personPick(this)"><datalist id="'+id+'-list"></datalist>'}
function existing(line,key){return String(line?.[key]??"")}
function blank(){return model.kind==="COAL"?{vehicleId:"",driverId:"",tripCount:"",routeId:""}:
 {excavatorId:"",patchCode:"",pointCode:"",routeId:"",tripCount:1}}
function fresh(count){model.lines=Array.from({length:count},()=>blank());model.card=null;model.clientKey=newKey();model.people={}}
async function fetchMasters(){
 const a=await Promise.all([
  api("/api/sites/KOCP/routes?kind=COAL"),
  api("/api/sites/KOCP/routes?kind=OB"),
  api("/api/site-ops/KOCP/lookups?kind=ASSET&activity=COAL&role=TRANSPORT&limit=250"),
  api("/api/site-ops/KOCP/lookups?kind=ASSET&activity=OB&role=TRANSPORT&limit=250"),
  api("/api/site-ops/KOCP/lookups?kind=ASSET&activity=OB&role=LOADING&limit=250"),
  api("/api/site-ops/KOCP/lookups?kind=MATERIAL&limit=100"),
  api("/api/site-ops/KOCP/lookups?kind=LOCATION&limit=100"),
  api(PREFIX+"/codes")
 ]);
 // A physical tipper can appear on Coal or OB paper even when its current
 // equipment operating group has not yet been corrected in Masters.
 // Offer the union of both *master-approved transport* lookup results.
 const transport=[...a[2],...a[3]].filter((row,i,items)=>
   items.findIndex(other=>other.id===row.id)===i);
 model.masters={COAL:a[0],OB:a[1],vehicles:transport,vehiclesOb:transport,excavators:a[4],
               materials:a[5],locations:a[6],codes:a[7]};
}
function h(id){return document.getElementById(id)}
function val(id){return h(id)?.value||""}
function availableShifts(){return (state.ctx?.shifts||[]).filter(x=>x.active!==false).map(x=>({id:x.shift,label:x.shift+" | "+(x.start||"")+"–"+(x.end||"")}))}
function lineHtml(line,i){
 if(model.kind==="COAL")return '<tr class="sr-row" data-no="'+i+'"><td>'+(i+1)+'</td>'+
 '<td><select id="srVehicle'+i+'">'+vehicleOptions("COAL",existing(line,"vehicleId"))+'</select></td>'+
 '<td>'+personInput("srDriver"+i,existing(line,"driverId"))+'</td>'+
 '<td><input class="sr-numeric" id="srCount'+i+'" type="number" min="1" max="200" step="1" value="'+esc(existing(line,"tripCount"))+'" oninput="KOCPSR.updateTotal()"></td>'+
 '<td><select id="srLineRoute'+i+'">'+routeOptions("COAL",existing(line,"routeId"))+'</select></td>'+
 '<td><button class="sr-small" type="button" onclick="KOCPSR.removeRow('+i+')">Remove</button></td></tr>';
 return '<tr class="sr-row" data-no="'+i+'"><td>'+(i+1)+'</td>'+
 '<td><select id="srExcavator'+i+'" onchange="KOCPSR.updateTotal()">'+opts(model.masters.excavators,existing(line,"excavatorId"),"Select excavator")+'</select></td>'+
 '<td><input list="srPatchList" id="srPatch'+i+'" value="'+esc(existing(line,"patchCode"))+'" oninput="KOCPSR.updateTotal()" placeholder="Patch master"></td>'+
 '<td><input list="srPointList" id="srPoint'+i+'" value="'+esc(existing(line,"pointCode"))+'" oninput="KOCPSR.updateTotal()" placeholder="Point master"></td>'+
 '<td><select id="srLineRoute'+i+'">'+routeOptions("OB",existing(line,"routeId"))+'</select></td>'+
 '<td><button class="sr-small" type="button" onclick="KOCPSR.removeRow('+i+')">Remove</button></td></tr>';
}
function groupOptionList(kind,id){return '<datalist id="'+id+'">'+model.masters.codes.filter(x=>x.kind===kind&&x.active).map(x=>
 '<option value="'+esc(x.code)+'" label="'+esc(x.name)+'"></option>').join('')+'</datalist>'}
function headerHtml(){
 const c=model.card||{},ob=model.kind==="OB";
 const d=c.operatingDate||state.ctx?.operatingDate||new Date().toISOString().slice(0,10);
 const shift=c.shift||state.ctx?.shift||"A";
 return '<div class="sr-head">'+paperInput("srDate",d,"Operating date","date")+
 selectBox("srShift","Shift",opts(availableShifts(),shift,"Choose shift"))+
 paperInput("srRef",c.sourceRef,"Paper reference (if provided)")+
 selectBox("srMaterial","Material",materialOptions(model.kind,c.materialId||""))+
 selectBox("srRoute","Default route / lead",routeOptions(model.kind,c.routeId||""))+
 (ob?selectBox("srHeaderVehicle","Tipper",vehicleOptions("OB",c.vehicleId||""))+
 '<label class="sr-field"><span>Driver</span>'+personInput("srHeaderDriver",c.driverId||"")+'</label>'+
 paperInput("srHmrOpen",c.openingHmr,"Opening HMR","number",'min="0" step="0.01"')+
 paperInput("srHmrClose",c.closingHmr,"Closing HMR","number",'min="0" step="0.01"')+
 paperInput("srKmrOpen",c.openingKmr,"Opening KMR","number",'min="0" step="0.1"')+
 paperInput("srKmrClose",c.closingKmr,"Closing KMR","number",'min="0" step="0.1"'):
 paperInput("srRelay",c.relayCode,"Relay code (from Masters)","text",'list="srRelayList"'))+
 paperInput("srDeclared",c.declaredTotal??"","Paper total trips (optional)","number",'min="0" step="1"')+
 '</div>';
}
function screen(){
 const ob=model.kind==="OB",card=model.card,status=card?.status||"NEW";
 const lines=card?.lines?.length?card.lines:model.lines;
 const total=lines.reduce((sum,x)=>sum+(model.kind==="COAL"?Number(x.tripCount||0):(
   x.excavatorId&&x.patchCode&&x.pointCode?1:0)),0);
 const extra=(ob?groupOptionList("PATCH","srPatchList")+groupOptionList("UNLOAD_POINT","srPointList"):
 groupOptionList("RELAY","srRelayList"));
 return '<section class="sr-workbench"><div class="sr-heading"><div><h1>Shift Production Register</h1>'+
 '<p>One source paper → verified MIS trips. No image upload or individual loading time.</p></div>'+
 '<div class="sr-badge">Status: '+esc(status)+'</div></div>'+
 '<div class="sr-tabs"><button type="button" class="'+(ob?'':'active')+'" onclick="KOCPSR.switchKind(\'COAL\')">Coal Register</button>'+
 '<button type="button" class="'+(ob?'active':'')+'" onclick="KOCPSR.switchKind(\'OB\')">OB Trip Cards</button></div>'+
 '<div class="sr-note">'+(ob?
 '<b>OB:</b> One card per tipper and shift. Each detail row is one actual trip. Select excavator, patch and unloading point from Masters.':
 '<b>Coal:</b> One sheet covers many drivers and vehicles. Enter the number of trips per vehicle row; do not enter 112 fictitious individual trip times.')+
 '</div><div class="sr-card"><h2>'+(ob?'OB Tipper Card Header':'Coal Shift Tripman Header')+'</h2>'+
 headerHtml()+extra+'</div>'+
 '<div class="sr-card"><div class="sr-toolbar"><h2>'+(ob?'Individual OB Trips':'Coal Vehicle/Driver Rows')+'</h2>'+
 '<strong>Total trips: <span id="srTotal">'+total+'</span></strong></div>'+
 '<div class="sr-scroll"><table class="sr-grid"><thead><tr>'+(ob?
 '<th>#</th><th>Excavator</th><th>Patch</th><th>Unloading Point</th><th>Route / Lead (override)</th><th></th>':
 '<th>#</th><th>Vehicle</th><th>Driver</th><th>Trip count</th><th>Route / Lead (override)</th><th></th>')+
 '</tr></thead><tbody id="srRows">'+lines.map((x,i)=>lineHtml(x,i)).join("")+'</tbody></table></div>'+
 '<div class="sr-actions"><button class="sr-small" type="button" onclick="KOCPSR.addRow(1)">+1 Row</button>'+
 '<button class="sr-small" type="button" onclick="KOCPSR.addRow(10)">+10 Rows</button>'+
 '<button class="sr-small" type="button" onclick="KOCPSR.copyDown()">Copy Down ↓</button></div></div>'+
 '<div class="sr-card"><div class="sr-toolbar"><h2>MIS Controls</h2><span>Save draft first; only the checker posts verified trips.</span></div>'+
 '<div class="sr-actions"><button class="sr-btn" type="button" onclick="KOCPSR.save()">Save Draft</button>'+
 '<button class="sr-btn" type="button" onclick="KOCPSR.submit()">Submit for Check</button>'+
 '<button class="sr-small" type="button" onclick="KOCPSR.newCard()">New '+model.kind+' Sheet</button>'+
 ((status==="SUBMITTED")?'<button class="sr-btn" type="button" onclick="KOCPSR.verify()">MIS Verify & Post</button>'+
 '<button class="sr-small" type="button" onclick="KOCPSR.reject()">Return for Correction</button>':'')+
 '</div><p class="sr-muted">Pending MCL factors do not prevent saving the source. Only verified cards become operational trips.</p>'+
 '<div id="srNotice" aria-live="polite"></div></div>'+
 '<div class="sr-card"><div class="sr-toolbar"><h2>Recent Shift Registers</h2>'+
 '<button class="sr-small" type="button" onclick="KOCPSR.history()">Refresh list</button></div>'+
 '<div id="srHistory" class="sr-muted">Loading saved records...</div></div>'+
 '<div class="sr-card"><div class="sr-toolbar"><h2>Relay / Patch / Unloading Point Masters</h2>'+
 '<span>Admin-controlled; code values are never hardcoded.</span></div><div class="sr-master">'+
 selectBox("srCodeKind","Master type",opts([{id:"RELAY",label:"Relay"},{id:"PATCH",label:"Patch"},{id:"UNLOAD_POINT",label:"Unloading Point"}],"","Choose master type"))+
 paperInput("srCode","Code") + paperInput("srCodeName","Description / Name") +
 selectBox("srCodeLocation","Linked physical location",opts(model.masters.locations,"","Unassigned (permitted for Relay/Patch)"))+
 '<button class="sr-small" type="button" onclick="KOCPSR.addMaster()">Add Single Master Entry</button></div>'+
 '<p class="sr-muted">Unloading points must be linked to their parent KOCP physical location before MIS verification.</p></div>'+
 '</section>';
}
function readRows(){
 const result=[];
 for(const tr of document.querySelectorAll("#srRows .sr-row")){
  const i=Number(tr.dataset.no),r={lineNo:i+1,routeId:val("srLineRoute"+i)};
  if(model.kind==="COAL"){r.vehicleId=val("srVehicle"+i);r.driverId=h("srDriver"+i)?.dataset.employeeId||"";r.tripCount=val("srCount"+i)}
  else{r.excavatorId=val("srExcavator"+i);r.patchCode=val("srPatch"+i).trim();r.pointCode=val("srPoint"+i).trim();r.tripCount=1}
  const has=model.kind==="COAL"?(Boolean(r.vehicleId||r.driverId||r.tripCount||r.routeId)):
   Boolean(r.excavatorId||r.patchCode||r.pointCode||r.routeId);
  if(has)result.push(r);
 }
 return result;
}
function values(){
 return {kind:model.kind,operatingDate:val("srDate"),shift:val("srShift"),sourceRef:val("srRef"),
 relayCode:model.kind==="COAL"?val("srRelay"):"",materialId:val("srMaterial"),
 routeId:val("srRoute"),vehicleId:model.kind==="OB"?val("srHeaderVehicle"):"",
 driverId:model.kind==="OB"?(h("srHeaderDriver")?.dataset.employeeId||""):"",
 openingHmr:model.kind==="OB"?val("srHmrOpen"):"",closingHmr:model.kind==="OB"?val("srHmrClose"):"",
 openingKmr:model.kind==="OB"?val("srKmrOpen"):"",closingKmr:model.kind==="OB"?val("srKmrClose"):"",
 declaredTotal:val("srDeclared")||null,
 lines:readRows()};
}
function notice(message,error=false){const n=h("srNotice");if(n){n.textContent=message;n.className=error?"sr-error":"sr-success"}else if(window.toast)toast(message,error?"bad":"good")}
function sync(){const inputs=values();model.lines=inputs.lines;model.pendingHeader=inputs}
async function renderSelf(){await fetchMasters();const w=h("workspace");if(w){w.innerHTML=screen();await history()}}
async function save(silent=false){
 try{
  const payload=values();payload.clientKey=model.clientKey||(model.clientKey=newKey());
  if(!payload.lines.length)throw Error("Enter at least one complete Coal/OB source row.");
  let data;
  if(model.card){
   if(!["DRAFT","REJECTED"].includes(model.card.status)){
    if(silent&&model.card.status==="SUBMITTED")return model.card;
    throw Error("This register is submitted/verified. Open a new sheet or return it for correction.");
   }
   payload.expectedVersion=model.card.version;
   data=await api(PREFIX+"/cards/"+enc(model.card.cardId),{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  }else{
   data=await api(PREFIX+"/cards",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  }
  model.card=data;model.lines=data.lines;model.clientKey=data.cardId||model.clientKey;
  if(!silent)notice("Draft saved. "+data.tripCount+" source trips recorded.");
  return data;
 }catch(e){notice(e.message,true);throw e}
}
async function submit(){
 try{
  const data=await save(true);
  if(data.status==="SUBMITTED"){notice("Already submitted for MIS review.");return}
  const r=await api(PREFIX+"/cards/"+enc(data.cardId)+"/submit",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({expectedVersion:data.version})});
  model.card=r;model.lines=r.lines;await renderSelf();notice("Submitted for MIS verification: "+r.tripCount+" trips.");
 }catch(e){notice(e.message,true)}
}
async function verify(){
 if(!model.card||model.card.status!=="SUBMITTED")return notice("Submit the register first.",true);
 if(!window.confirm("Verify this paper register and post its trip counts to KOCP production?"))return;
 try{
  const r=await api(PREFIX+"/cards/"+enc(model.card.cardId)+"/decision",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({action:"VERIFY",expectedVersion:model.card.version})});
  model.card=r;model.lines=r.lines;await renderSelf();
  notice("MIS verified: "+r.tripCount+" trips. Quantity pending factors: "+r.pendingFactorTrips+".");
 }catch(e){notice(e.message,true)}
}
async function reject(){
 if(!model.card||model.card.status!=="SUBMITTED")return;
 const reason=window.prompt("Reason for returning this register to MIS for correction:");
 if(!reason)return;
 try{
  const r=await api(PREFIX+"/cards/"+enc(model.card.cardId)+"/decision",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({action:"REJECT",reason,expectedVersion:model.card.version})});
  model.card=r;model.lines=r.lines;await renderSelf();notice("Returned for correction.");
 }catch(e){notice(e.message,true)}
}
async function history(){
 const day=val("srDate")||state.ctx?.operatingDate;
 try{
 const rows=await api(PREFIX+"/cards?operating_date="+enc(day)+"&kind="+enc(model.kind));
 const out=h("srHistory");if(!out)return;
 out.innerHTML=!rows.length?"No source registers saved for this date.":
 '<div class="sr-scroll"><table class="sr-grid"><thead><tr><th>Shift</th><th>Source ref</th><th>Rows</th><th>Trips</th><th>Status</th><th>Action</th></tr></thead><tbody>'+
 rows.map(x=>'<tr><td>'+esc(x.shift)+'</td><td>'+esc(x.sourceRef||x.cardId)+'</td>'+
 '<td>'+x.rowCount+'</td><td>'+x.tripCount+'</td><td>'+esc(x.status)+'</td><td>'+
 '<button class="sr-small" type="button" onclick="KOCPSR.open(\''+esc(x.cardId)+'\')">Open</button></td></tr>').join("")+
 '</tbody></table></div>';
 }catch(e){const out=h("srHistory");if(out)out.textContent=e.message}
}
async function open(id){try{const r=await api(PREFIX+"/cards/"+enc(id));model.kind=r.kind;model.card=r;model.lines=r.lines;model.clientKey=r.cardId;await renderSelf()}catch(e){notice(e.message,true)}}
function updateTotal(){const el=h("srTotal");if(!el)return;
 if(model.kind==="COAL"){el.textContent=[...document.querySelectorAll("#srRows .sr-numeric")].reduce((s,x)=>s+(Number(x.value)||0),0);return}
 el.textContent=[...document.querySelectorAll("#srRows .sr-row")].filter(x=>{
   const i=x.dataset.no;return val("srExcavator"+i)&&val("srPatch"+i)&&val("srPoint"+i)
 }).length;
}
function addRow(n){sync();for(let i=0;i<n;i++)model.lines.push(blank());h("srRows").innerHTML=model.lines.map(lineHtml).join("");updateTotal()}
function removeRow(i){sync();model.lines.splice(i,1);if(!model.lines.length)model.lines=[blank()];h("srRows").innerHTML=model.lines.map(lineHtml).join("");updateTotal()}
function copyDown(){sync();const a=model.lines.at(-1);if(!a)return;const next={...a};
 if(model.kind==="COAL"){next.tripCount="";next.driverId="";next.vehicleId=""}
 model.lines.push(next);h("srRows").innerHTML=model.lines.map(lineHtml).join("");updateTotal()}
function switchKind(kind){if(model.kind===kind)return;if(!window.confirm("Switching registers will clear unsaved screen changes. Continue?"))return;model.kind=kind;fresh(kind==="COAL"?24:10);renderSelf()}
function newCard(){if(!window.confirm("Start a fresh source register? Save current work first."))return;fresh(model.kind==="COAL"?24:10);renderSelf()}
async function addMaster(){
 const kind=val("srCodeKind"),code=val("srCode").trim(),name=val("srCodeName").trim(),locationId=val("srCodeLocation");
 if(!kind||!code||!name)return notice("Enter master type, code and name.",true);
 try{
 await api(PREFIX+"/codes",{method:"POST",headers:{"Content-Type":"application/json"},
 body:JSON.stringify({kind,code,name,locationId})});
 sync();await renderSelf();notice(kind+" "+code+" added to Masters.");
 }catch(e){notice(e.message,true)}
}
let personTimers={};
function personSearch(el){
 el.dataset.employeeId="";
 clearTimeout(personTimers[el.id]);
 const q=el.value.trim();if(q.length<2)return;
 personTimers[el.id]=setTimeout(async()=>{
 try{
 const rows=await api("/api/site-ops/KOCP/lookups?kind=EMPLOYEE&q="+enc(q)+"&limit=60");
 model.people[el.id]=rows;
 const list=h(el.id+"-list");
 if(list)list.innerHTML=rows.map(x=>'<option value="'+esc(x.label+" — "+x.id)+'"></option>').join("");
 }catch(e){console.warn("Employee lookup unavailable",e)}
 },220);
}
function personPick(el){
 const name=el.value.trim(),list=model.people[el.id]||[];
 const found=list.find(x=>(x.label+" — "+x.id)===name||x.id===name);
 if(found){el.dataset.employeeId=found.id;el.value=found.label+" — "+found.id}
}
async function renderKocpShiftRegister(){
 if(!model.lines.length){fresh(24)}
 await fetchMasters();
 return screen();
}
window.renderKocpShiftRegister=renderKocpShiftRegister;
window.KOCPSR={save:()=>save().catch(()=>{}),submit,verify,reject,history,open,updateTotal,addRow,removeRow,
 copyDown,switchKind,newCard,addMaster,personSearch,personPick,afterRender:history};
})();
