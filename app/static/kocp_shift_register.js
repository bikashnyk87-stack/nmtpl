/* KOCP Shift MIS Register — paper-first Coal (aggregate) and OB (individual).
   No photos, no per-trip times; all operational options are supplied by Masters.
*/
(function(){
"use strict";
const PREFIX="/api/KOCP/shift-register";
const model={kind:"COAL",card:null,clientKey:null,lines:[],masters:{COAL:[],OB:[],codes:[],vehicles:[],excavators:[],materials:[],locations:[]},drivers:[],driverError:""};
function enc(v){return encodeURIComponent(String(v||""))}
function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function newKey(){return (window.crypto?.randomUUID?.()||String(Date.now())+"-"+Math.random()).slice(0,120)}
function opts(items,value,placeholder="Choose from Masters"){
 return '<option value="">'+esc(placeholder)+'</option>'+items.map(x=>
 '<option value="'+esc(x.id||x.routeId||x.code)+'" '+((x.id||x.routeId||x.code)===value?'selected':'')+'>'+esc(x.label||x.name||x.title||x.code)+'</option>').join('');
}
function retainedOptions(items,value,placeholder){
 const available=value&&!items.some(x=>x.id===value)
  ? [...items,{id:value,label:value+" — previously saved; check Masters"}] : items;
 return opts(available,value,placeholder);
}
function codeOptions(kind,value){
 const items=model.masters.codes.filter(x=>x.kind===kind&&x.active&&(kind==="RELAY"||x.locationId))
  .map(x=>({id:x.code,label:x.code+" — "+x.name+(x.locationName?" · "+x.locationName:"")}));
 return retainedOptions(items,value,items.length?"Select from Masters":"No mapped options in KOCP Masters");
}
function vehicleOptions(activity,value){
 return retainedOptions(activity==="COAL"?model.masters.vehicles:model.masters.vehiclesOb,value,"Select tipper / door number");
}
const locationPrefix="location:";
function pointValue(line,codeKey,locationKey){
 return line[codeKey]||(line[locationKey]?locationPrefix+line[locationKey]:"");
}
function locationIdFor(kind,value){
 if(value.startsWith(locationPrefix))return value.slice(locationPrefix.length);
 return model.masters.codes.find(x=>x.kind===kind&&x.code===value&&x.active)?.locationId;
}
function locationOptions(kind,value){
 const endpoint=kind==="PATCH"?"sourceLocationId":"destinationLocationId";
 const routePoints=new Set(model.masters.OB.filter(r=>r.active).map(r=>r[endpoint]));
 const locations=model.masters.locations.filter(x=>routePoints.has(x.id))
  .map(x=>({id:locationPrefix+x.id,label:x.label}));
 const codes=model.masters.codes.filter(x=>x.kind===kind&&x.active&&routePoints.has(x.locationId))
  .map(x=>({id:x.code,label:x.code+" — "+x.name+" · "+x.locationName}));
 return retainedOptions([...locations,...codes],value,
  locations.length||codes.length?"Select from Location Master":"No active locations for this field");
}
function matchingRoutes(kind,patch="",point=""){
 const source=locationIdFor("PATCH",patch),destination=locationIdFor("UNLOAD_POINT",point);
 if((patch&&!source)||(point&&!destination))return [];
 return model.masters[kind].filter(x=>x.active&&
  (!source||x.sourceLocationId===source)&&(!destination||x.destinationLocationId===destination));
}
function routeOptions(kind,value,patch="",point="",retain=true){
 const items=matchingRoutes(kind,patch,point).map(r=>({
  id:r.routeId,label:r.group+" → "+r.destination+" | "+r.category+" | "+r.distanceRange
 }));
 const placeholder=items.length?"Select approved route / lead":"No matching route in KOCP Masters";
 return retain?retainedOptions(items,value,placeholder):opts(items,value,placeholder);
}
function materialOptions(kind,value){return retainedOptions(model.masters.materials.filter(x=>
 kind==="OB"?["CUM","M3","M³"].includes(String(x.unit||"").toUpperCase()):
 String(x.unit||"").toUpperCase()==="MT"),value,"Select "+kind+" material")}
function paperInput(id,value,label,type="text",attrs=""){return '<label class="sr-field"><span>'+esc(label)+'</span><input id="'+id+'" type="'+type+'" value="'+esc(value||"")+'" '+attrs+'></label>'}
function selectBox(id,label,html){return '<label class="sr-field"><span>'+esc(label)+'</span><select id="'+id+'">'+html+'</select></label>'}
function driverOptions(value){
 return retainedOptions(model.drivers,value,model.driverError||(
  model.drivers.length?"Select driver / employee code":"No eligible KOCP drivers for this date"));
}
function driverSelect(id,value){
 return '<select id="'+id+'" data-sr-driver aria-label="Driver">'+driverOptions(value)+'</select>';
}
function cardDate(){
 return model.card?.operatingDate||state.ctx?.operatingDate||new Date().toISOString().slice(0,10);
}
async function fetchDrivers(day){
 try{
  return {rows:await api(PREFIX+"/drivers?operating_date="+enc(day)),error:""};
 }catch(e){
  return {rows:[],error:"Employee Master could not be loaded"};
 }
}
function fetchAssets(day){
 const path="/api/site-ops/KOCP/lookups?kind=ASSET&limit=250&operating_date="+enc(day);
 return Promise.all([
  api(path+"&activity=COAL&role=TRANSPORT"),
  api(path+"&activity=OB&role=TRANSPORT"),
  api(path+"&activity=OB&role=LOADING").then(rows=>rows.filter(x=>x.category==="EXCAVATOR"))
 ]);
}
async function changeDate(){
 const dateField=h("srDate"), day=dateField.value;
 const [result,assets]=day?await Promise.all([
  fetchDrivers(day),fetchAssets(day).catch(()=>null)
 ]):[{rows:[],error:"Select an operating date"},[[],[],[]]];
 if(h("srDate")!==dateField||dateField.value!==day)return;
 model.drivers=result.rows;
 model.driverError=result.error;
 for(const select of document.querySelectorAll("[data-sr-driver]")){
  const current=select.value;
  select.innerHTML=driverOptions(result.error||model.drivers.some(x=>x.id===current)?current:"");
 }
 if(assets){
  [model.masters.vehicles,model.masters.vehiclesOb,model.masters.excavators]=assets;
 }
 for(const select of document.querySelectorAll("[data-sr-asset]")){
  const items=assets?model.masters[select.dataset.srAsset]:[];
  const current=select.value;
  select.innerHTML=retainedOptions(items,!assets||items.some(x=>x.id===current)?current:"",
   assets?"Select from Masters":"Equipment Master could not be loaded");
 }
 await Promise.all([history(),loadSummary()]);
}
function existing(line,key){return String(line?.[key]??"")}
function blank(){return model.kind==="COAL"?{vehicleId:"",driverId:"",tripCount:"",routeId:""}:
 {excavatorId:"",patchCode:"",pointCode:"",routeId:"",tripCount:""}}
function fresh(count){model.lines=Array.from({length:count},()=>blank());model.card=null;model.clientKey=newKey()}
async function fetchMasters(){
 const a=await Promise.all([
  api("/api/sites/KOCP/routes?kind=COAL"),
  api("/api/sites/KOCP/routes?kind=OB"),
  fetchAssets(cardDate()),
  api("/api/site-ops/KOCP/lookups?kind=MATERIAL&limit=100"),
  api(PREFIX+"/codes"),
  fetchDrivers(cardDate()),
  api("/api/site-ops/KOCP/lookups?kind=LOCATION&limit=100")
 ]);
 model.masters={COAL:a[0],OB:a[1],vehicles:a[2][0],vehiclesOb:a[2][1],excavators:a[2][2],
               materials:a[3],codes:a[4],locations:a[6]};
 model.drivers=a[5].rows;
 model.driverError=a[5].error;
}
function h(id){return document.getElementById(id)}
function val(id){return h(id)?.value||""}
function availableShifts(){return (state.ctx?.shifts||[]).filter(x=>x.active!==false).map(x=>({id:x.shift,label:x.shift+" | "+(x.start||"")+"–"+(x.end||"")}))}
function lineHtml(line,i){
 if(model.kind==="COAL")return '<tr class="sr-row" data-no="'+i+'"><td>'+(i+1)+'</td>'+
 '<td><select data-sr-asset="vehicles" id="srVehicle'+i+'">'+vehicleOptions("COAL",existing(line,"vehicleId"))+'</select></td>'+
 '<td>'+driverSelect("srDriver"+i,existing(line,"driverId"))+'</td>'+
 '<td><input class="sr-numeric" id="srCount'+i+'" type="number" min="1" max="200" step="1" value="'+esc(existing(line,"tripCount"))+'" oninput="KOCPSR.updateTotal()"></td>'+
 '<td><select id="srLineRoute'+i+'">'+routeOptions("COAL",existing(line,"routeId"))+'</select></td>'+
 '<td><button class="sr-small" type="button" onclick="KOCPSR.removeRow('+i+')">Remove</button></td></tr>';
 const patch=pointValue(line,"patchCode","sourceLocationId");
 const point=pointValue(line,"pointCode","destinationLocationId");
 return '<tr class="sr-row" data-no="'+i+'"><td>'+(i+1)+'</td>'+
 '<td><select data-sr-asset="excavators" id="srExcavator'+i+'" onchange="KOCPSR.updateTotal()">'+retainedOptions(model.masters.excavators,existing(line,"excavatorId"),"Select excavator")+'</select></td>'+
 '<td><select id="srPatch'+i+'" aria-label="Loading patch" onchange="KOCPSR.changePoints('+i+')">'+
 locationOptions("PATCH",patch)+'</select></td>'+
 '<td><select id="srPoint'+i+'" aria-label="Unloading point" onchange="KOCPSR.changePoints('+i+')">'+
 locationOptions("UNLOAD_POINT",point)+'</select></td>'+
 '<td><select id="srLineRoute'+i+'" aria-label="Route / Lead">'+
 routeOptions("OB",existing(line,"routeId"),patch,point)+'</select></td>'+
 '<td><input class="sr-numeric" aria-label="Trips" id="srCount'+i+'" type="number" min="1" max="200" step="1" value="'+esc(existing(line,"tripCount"))+'" oninput="KOCPSR.updateTotal()"></td>'+
 '<td><button class="sr-small" type="button" onclick="KOCPSR.removeRow('+i+')">Remove</button></td></tr>';
}
function changePoints(i){
 const select=h("srLineRoute"+i),patch=val("srPatch"+i),point=val("srPoint"+i);
 const matches=matchingRoutes("OB",patch,point);
 const previous=select.value, defaultRoute=val("srRoute");
 const selected=matches.some(x=>x.routeId===previous)?previous:
  patch&&point&&matches.length===1&&matches[0].routeId!==defaultRoute?matches[0].routeId:"";
 select.innerHTML=routeOptions("OB",selected,patch,point,false);
 updateTotal();
}
function headerHtml(){
 const c=model.card||{},ob=model.kind==="OB";
 const d=cardDate();
 const shift=c.shift||state.ctx?.shift||"A";
 return '<div class="sr-head">'+paperInput("srDate",d,"Operating date","date",'onchange="KOCPSR.changeDate()"')+
 selectBox("srShift","Shift",opts(availableShifts(),shift,"Choose shift"))+
 selectBox("srMaterial","Material",materialOptions(model.kind,c.materialId||""))+
 (ob?'<label class="sr-field"><span>Tipper</span><select id="srHeaderVehicle" data-sr-asset="vehiclesOb">'+vehicleOptions("OB",c.vehicleId||"")+'</select></label>'+
 '<label class="sr-field"><span>Driver</span>'+driverSelect("srHeaderDriver",c.driverId||"")+'</label>':
 selectBox("srRelay","Relay",codeOptions("RELAY",c.relayCode||"")))+
 paperInput("srDeclared",c.declaredTotal??"","Paper trip total","number",'min="0" step="1"')+
 '</div><details class="sr-card-details"><summary>Paper reference'+(ob?' and meters':' and route')+'</summary><div class="sr-head">'+
 paperInput("srRef",c.sourceRef,"Paper reference")+
 selectBox("srRoute","Default route / lead",routeOptions(model.kind,c.routeId||""))+
 (ob?paperInput("srHmrOpen",c.openingHmr,"Opening HMR","number",'min="0" step="0.01"')+
 paperInput("srHmrClose",c.closingHmr,"Closing HMR","number",'min="0" step="0.01"')+
 paperInput("srKmrOpen",c.openingKmr,"Opening KMR","number",'min="0" step="0.1"')+
 paperInput("srKmrClose",c.closingKmr,"Closing KMR","number",'min="0" step="0.1"'):"")+
 '</div></details>';
}
function screen(){
 const ob=model.kind==="OB",card=model.card,status=card?.status||"NEW";
 const lines=card?.lines?.length?card.lines:model.lines;
 const total=lines.reduce((sum,line)=>sum+Number(line.tripCount||0),0);
 return '<section class="sr-workbench"><div class="sr-heading"><div><h1>Shift Production Register</h1>'+
 '</div>'+
 '<div class="sr-badge">Status: '+esc(status)+'</div></div>'+
 '<div class="sr-tabs"><button type="button" class="'+(ob?'':'active')+'" onclick="KOCPSR.switchKind(\'COAL\')">Coal Register</button>'+
 '<button type="button" class="'+(ob?'active':'')+'" onclick="KOCPSR.switchKind(\'OB\')">OB Trip Cards</button></div>'+
 '<div class="sr-card"><h2>'+(ob?'Tipper Card':'Coal Shift Sheet')+'</h2>'+
 headerHtml()+'</div>'+
 '<div class="sr-card"><div class="sr-toolbar"><h2>'+(ob?'OB Trip Counts':'Coal Vehicle/Driver Rows')+'</h2>'+
 '<div class="sr-entry-actions"><strong>Trips: <span id="srTotal">'+total+'</span></strong>'+
 '<button class="sr-small" type="button" onclick="KOCPSR.addRow()">Add row</button>'+
 '<button class="sr-small" type="button" onclick="KOCPSR.copyDown()">Copy down</button></div></div>'+
 '<div class="sr-scroll sr-entry-scroll" tabindex="0" aria-label="Trip entry rows"><table class="sr-grid"><thead><tr>'+(ob?
 '<th>#</th><th>Excavator</th><th>Patch</th><th>Unloading Point</th><th>Route / Lead</th><th>Trips</th><th></th>':
 '<th>#</th><th>Vehicle</th><th>Driver</th><th>Trip count</th><th>Route / Lead (override)</th><th></th>')+
 '</tr></thead><tbody id="srRows">'+lines.map((x,i)=>lineHtml(x,i)).join("")+'</tbody></table></div>'+
 '</div>'+
 '<div class="sr-card">'+
 '<div class="sr-actions"><button class="sr-btn" type="button" onclick="KOCPSR.save()">Save Draft</button>'+
 '<button class="sr-btn" type="button" onclick="KOCPSR.submit()">Submit for Check</button>'+
 '<button class="sr-small" type="button" onclick="KOCPSR.newCard()">New '+model.kind+' Sheet</button>'+
 ((status==="SUBMITTED")?'<button class="sr-btn" type="button" onclick="KOCPSR.verify()">MIS Verify & Post</button>'+
 '<button class="sr-small" type="button" onclick="KOCPSR.reject()">Return for Correction</button>':'')+
 '</div>'+
 '<div id="srNotice" aria-live="polite"></div></div>'+
 '<details class="sr-card"><summary>Shift MIS Summary</summary>'+
 '<div id="srSummary" class="sr-muted">Loading verified totals...</div></details>'+
 '<details class="sr-card"><summary>Recent Shift Registers</summary><div class="sr-toolbar">'+
 '<button class="sr-small" type="button" onclick="KOCPSR.history()">Refresh list</button></div>'+
 '<div id="srHistory" class="sr-muted">Loading saved records...</div></details>'+
 '</section>';
}
function readRows(includeBlank=false){
 const result=[];
 for(const tr of document.querySelectorAll("#srRows .sr-row")){
  const i=Number(tr.dataset.no),r={lineNo:i+1,routeId:val("srLineRoute"+i)};
  if(model.kind==="COAL"){r.vehicleId=val("srVehicle"+i);r.driverId=val("srDriver"+i);r.tripCount=val("srCount"+i)}
  else{
   r.excavatorId=val("srExcavator"+i);
   const patch=val("srPatch"+i),point=val("srPoint"+i);
   r.patchCode=patch.startsWith(locationPrefix)?"":patch;
   r.pointCode=point.startsWith(locationPrefix)?"":point;
   r.sourceLocationId=locationIdFor("PATCH",patch)||"";
   r.destinationLocationId=locationIdFor("UNLOAD_POINT",point)||"";
   r.tripCount=val("srCount"+i);
  }
  const has=model.kind==="COAL"?(Boolean(r.vehicleId||r.driverId||r.tripCount||r.routeId)):
   Boolean(r.excavatorId||r.patchCode||r.pointCode||r.sourceLocationId||r.destinationLocationId||r.routeId||r.tripCount);
  if(includeBlank||has)result.push(r);
 }
 return result;
}
function values(){
 return {kind:model.kind,operatingDate:val("srDate"),shift:val("srShift"),sourceRef:val("srRef"),
 relayCode:model.kind==="COAL"?val("srRelay"):"",materialId:val("srMaterial"),
 routeId:val("srRoute"),vehicleId:model.kind==="OB"?val("srHeaderVehicle"):"",
 driverId:model.kind==="OB"?val("srHeaderDriver"):"",
 openingHmr:model.kind==="OB"?val("srHmrOpen"):"",closingHmr:model.kind==="OB"?val("srHmrClose"):"",
 openingKmr:model.kind==="OB"?val("srKmrOpen"):"",closingKmr:model.kind==="OB"?val("srKmrClose"):"",
 declaredTotal:val("srDeclared")||null,
 lines:readRows()};
}
function notice(message,error=false){const n=h("srNotice");if(n){n.textContent=message;n.className=error?"sr-error":"sr-success"}else if(window.toast)toast(message,error?"bad":"good")}
function sync(){const inputs=values();model.lines=readRows(true);model.pendingHeader=inputs}
async function renderSelf(){await fetchMasters();const w=h("workspace");if(w){w.innerHTML=screen();await Promise.all([history(),loadSummary()])}}
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
async function loadSummary(){
 const day=val("srDate")||state.ctx?.operatingDate;
 try{
  const result=await api(PREFIX+"/summary?operating_date="+enc(day));
  const out=h("srSummary");if(!out)return;
  out.innerHTML='<div class="sr-summary">'+["COAL","OB"].map(kind=>{
   const v=result.kinds[kind]||{};
   return '<div class="sr-summary-item"><b>'+esc(kind)+'</b>'+
    '<strong>'+Number(v.trips||0)+' verified trips</strong>'+
    '<small>'+Number(v.verified||0)+'/'+Number(v.cards||0)+' registers verified · '+
    Number(v.pendingFactorTrips||0)+' trips pending MCL quantity</small></div>';
  }).join("")+'</div>';
 }catch(e){const out=h("srSummary");if(out)out.textContent=e.message}
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
function updateTotal(){
 const el=h("srTotal");if(!el)return;
 el.textContent=[...document.querySelectorAll("#srRows .sr-numeric")]
  .reduce((sum,input)=>sum+(Number(input.value)||0),0);
}
function redrawRows(focusIndex){
 h("srRows").innerHTML=model.lines.map(lineHtml).join("");
 updateTotal();
 if(focusIndex!==undefined){
  h((model.kind==="OB"?"srExcavator":"srVehicle")+focusIndex)?.focus();
 }
}
function addRow(){
 sync();
 const empty=model.lines.findIndex(row=>!Object.entries(row).some(([key,value])=>key!=="lineNo"&&value));
 if(empty>=0)return redrawRows(empty);
 if(model.lines.length>=200)return notice("Maximum 200 rows per sheet.",true);
 model.lines.push(blank());
 redrawRows(model.lines.length-1);
}
function removeRow(i){
 sync();model.lines.splice(i,1);if(!model.lines.length)model.lines=[blank()];
 redrawRows();
}
function copyDown(){
 sync();
 const index=model.lines.findLastIndex(row=>model.kind==="COAL"?row.vehicleId:row.excavatorId);
 if(index<0)return notice("Select equipment before copying a row.",true);
 const next={...model.lines[index],tripCount:""};
 if(model.kind==="COAL"){next.driverId="";next.vehicleId=""}
 const empty=model.lines.findIndex((row,i)=>i>index&&
  !Object.entries(row).some(([key,value])=>key!=="lineNo"&&value));
 if(empty>=0){model.lines[empty]=next;return redrawRows(empty)}
 if(model.lines.length>=200)return notice("Maximum 200 rows per sheet.",true);
 model.lines.push(next);redrawRows(model.lines.length-1);
}
function switchKind(kind){if(model.kind===kind)return;if(!window.confirm("Switching registers will clear unsaved screen changes. Continue?"))return;model.kind=kind;fresh(kind==="COAL"?4:2);renderSelf()}
function newCard(){if(!window.confirm("Start a fresh source register? Save current work first."))return;fresh(model.kind==="COAL"?4:2);renderSelf()}
const masterKinds=[{id:"RELAY",label:"Coal relay"},{id:"PATCH",label:"OB loading patch"},
 {id:"UNLOAD_POINT",label:"OB unloading point"}];
let codeRows=[];
async function renderCodeMasters(locations){
 codeRows=await api(PREFIX+"/codes");
 const locationOptions=locations.filter(l=>l.active).map(l=>({id:l.locationId,label:l.code+" — "+l.name}));
 const rows=codeRows.map((r,i)=>'<tr><td>'+esc(masterKinds.find(x=>x.id===r.kind)?.label||r.kind)+'</td><td>'+
  esc(r.code)+'</td><td>'+esc(r.name)+'</td><td>'+esc(r.locationName||
  (r.kind==="RELAY"?"—":"Mapping required"))+'</td><td>'+(r.active?"Active":"Inactive")+
  '</td><td><button type="button" class="sr-small" onclick="KOCPSR.editCode('+i+')">Edit</button></td></tr>').join("");
 return '<section class="sr-card"><h2>Coal Relay and OB Location Codes</h2>'+
  '<div class="sr-master">'+selectBox("srCodeKind","Master type",opts(masterKinds,"","Choose master type"))+
  paperInput("srCode","","Code")+paperInput("srCodeName","","Name")+
  selectBox("srCodeLocation","ERP location",opts(locationOptions,"","Choose a location"))+
  '<label><input id="srCodeActive" type="checkbox" checked> Active</label>'+
  '<button type="button" class="sr-small" onclick="KOCPSR.saveCode()">Save</button>'+
  '<button type="button" class="sr-small" onclick="KOCPSR.editCode(-1)">New</button></div>'+
  '<div class="sr-scroll"><table class="sr-grid"><thead><tr><th>Type</th><th>Code</th><th>Name</th>'+
  '<th>ERP location</th><th>Status</th><th></th></tr></thead><tbody>'+rows+'</tbody></table></div></section>';
}
function editCode(i){
 const row=codeRows[i];
 h("srCodeKind").value=row?.kind||"";
 h("srCode").value=row?.code||"";
 h("srCodeName").value=row?.name||"";
 h("srCodeLocation").value=row?.locationId||"";
 h("srCodeActive").checked=row?.active??true;
 h("srCodeKind").disabled=h("srCode").disabled=Boolean(row);
 h("srCodeActive").disabled=!row;
}
async function saveCode(){
 const kind=val("srCodeKind"),code=val("srCode").trim(),name=val("srCodeName").trim();
 const editing=h("srCode").disabled;
 try{
  await api(PREFIX+"/codes",{
   method:editing?"PUT":"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify({kind,code,name,locationId:val("srCodeLocation"),active:h("srCodeActive").checked})
  });
  await window.render();
  toast("KOCP Master code saved");
 }catch(e){toast(e.message,"bad")}
}
async function renderKocpShiftRegister(){
 if(!model.lines.length){fresh(4)}
 await fetchMasters();
 return screen();
}
window.renderKocpShiftRegister=renderKocpShiftRegister;
window.KOCPSR={save:()=>save().catch(()=>{}),submit,verify,reject,history,open,updateTotal,addRow,removeRow,
 copyDown,switchKind,newCard,renderCodeMasters,editCode,saveCode,changeDate,changePoints,afterRender:async()=>{await Promise.all([history(),loadSummary()])}};
})();
