/* KOCP Shift MIS Register — paper-first Coal (aggregate) and OB (individual).
   No photos, no per-trip times; all operational options are supplied by Masters.
*/
(function(){
"use strict";
const PREFIX="/api/KOCP/shift-register";
const model={kind:"COAL",card:null,clientKey:null,lines:[],masters:{COAL:[],OB:[],codes:[],vehicles:[],excavators:[],loadingCoal:[],materials:[],locations:[]},drivers:[],driverError:""};
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
  model.drivers.length?"Driver optional — select from Masters":"Driver optional — leave blank if not available"));
}
function driverSelect(id,value){
 return '<select id="'+id+'" data-sr-driver aria-label="Driver (optional)">'+driverOptions(value)+'</select>';
}

/* Type-to-search controls retain existing <select> IDs and master-backed values. */
function closeSearchDropdowns(except){
 document.querySelectorAll(".sr-combo").forEach(box=>{if(box!==except)box._srClose?.()});
}
function refreshSearchDropdown(select){select?.closest(".sr-combo")?._srRefresh?.()}
function enhanceSearchDropdowns(scope){
 if(!scope)return;
 scope.querySelectorAll("select[id]").forEach(select=>{
  if(select.id==="srShift"||select.closest(".sr-combo"))return;
  const box=document.createElement("div");box.className="sr-combo";
  select.parentNode.insertBefore(box,select);box.appendChild(select);
  select.classList.add("sr-combo-source");select.tabIndex=-1;
  const input=document.createElement("input");
  input.type="search";input.autocomplete="off";input.className="sr-combo-input";
  const field=box.closest(".sr-field");
  const label=select.getAttribute("aria-label")||field?.querySelector("span")?.textContent||select.id;
  input.setAttribute("aria-label","Search "+label+" from Masters");
  input.setAttribute("role","combobox");input.setAttribute("aria-autocomplete","list");
  input.setAttribute("aria-expanded","false");
  const menu=document.createElement("div");menu.className="sr-combo-menu";
  menu.id="srComboList-"+select.id;menu.setAttribute("role","listbox");
  input.setAttribute("aria-controls",menu.id);
  box.insertBefore(input,select);box.appendChild(menu);
  let choices=[],active=0;
  const selectedLabel=()=>select.selectedOptions?.[0]?.value?select.selectedOptions[0].textContent:"";
  const close=()=>{menu.style.display="none";input.setAttribute("aria-expanded","false");input.removeAttribute("aria-activedescendant")};
  function mark(){
   const items=menu.querySelectorAll(".sr-combo-option");
   items.forEach((b,i)=>{b.classList.toggle("active",i===active);b.setAttribute("aria-selected",String(i===active))});
   if(items[active]){input.setAttribute("aria-activedescendant",items[active].id);items[active].scrollIntoView({block:"nearest"})}
  }
  function choose(choice){
   select.value=choice.value;input.value=choice.textContent;
   input.setAttribute("aria-invalid","false");close();
   select.dispatchEvent(new Event("change",{bubbles:true}));
  }
  function show(query){
   closeSearchDropdowns(box);
   const filter=String(query||"").trim().toLocaleLowerCase();
   choices=[...select.options].filter(o=>o.value&&!o.disabled&&(!filter||o.textContent.toLocaleLowerCase().includes(filter))).slice(0,60);
   menu.replaceChildren();
   choices.forEach((choice,i)=>{
    const b=document.createElement("button");b.type="button";
    b.className="sr-combo-option";b.id=menu.id+"-"+i;
    b.setAttribute("role","option");b.textContent=choice.textContent;
    b.addEventListener("mousedown",e=>e.preventDefault());
    b.addEventListener("click",()=>choose(choice));menu.appendChild(b);
   });
   if(!choices.length){
    const empty=document.createElement("div");empty.className="sr-combo-empty";
    empty.textContent="No matching approved master option";menu.appendChild(empty);
   }
   const r=input.getBoundingClientRect(),width=Math.min(Math.max(r.width,290),window.innerWidth-16);
   menu.style.left=Math.max(8,Math.min(r.left,window.innerWidth-width-8))+"px";menu.style.width=width+"px";
   const below=window.innerHeight-r.bottom-8,above=r.top-8;
   menu.style.maxHeight=Math.min(240,Math.max(100,below<170&&above>below?above:below))+"px";
   menu.style.top=(below<170&&above>below?Math.max(8,r.top-Math.min(240,above)):r.bottom+3)+"px";
   menu.style.display="block";input.setAttribute("aria-expanded","true");
   active=0;mark();
  }
  box._srClose=close;
  box._srRefresh=()=>{
   input.value=selectedLabel();input.placeholder=select.options[0]?.textContent||"Search approved Masters";
   input.setAttribute("aria-invalid","false");close();
  };
  input.addEventListener("focus",()=>{input.select();show("")});
  input.addEventListener("input",()=>{
   input.setAttribute("aria-invalid",String(input.value.trim()!==selectedLabel().trim()));show(input.value);
  });
  input.addEventListener("keydown",e=>{
   if(e.key==="Escape"){e.preventDefault();box._srRefresh();return}
   if(e.key==="ArrowDown"||e.key==="ArrowUp"){
    e.preventDefault();
    if(menu.style.display==="none")show(input.value);
    else if(choices.length){active=Math.max(0,Math.min(choices.length-1,active+(e.key==="ArrowDown"?1:-1)));mark()}
   }else if(e.key==="Enter"&&menu.style.display!=="none"){
    e.preventDefault();if(choices[active])choose(choices[active]);
   }
  });
  input.addEventListener("blur",()=>setTimeout(close,150));
  box._srRefresh();
 });
}
function validateSearchDropdowns(){
 for(const box of document.querySelectorAll(".sr-workbench .sr-combo")){
  const select=box.querySelector("select"),input=box.querySelector(".sr-combo-input");
  const chosen=select.selectedOptions?.[0]?.value?select.selectedOptions[0].textContent:"";
  if(input.value.trim()!==chosen.trim()){
   input.focus();throw Error("Choose a matching approved master option from the search results before saving.");
  }
 }
}
document.addEventListener("pointerdown",e=>{if(!e.target.closest?.(".sr-combo"))closeSearchDropdowns()});
document.addEventListener("change",e=>{if(e.target?.id==="srShift")loadMeterRows()});
document.addEventListener("scroll",e=>{if(!e.target.closest?.(".sr-combo-menu"))closeSearchDropdowns()},true);

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
  api(path+"&activity=OB&role=LOADING").then(rows=>rows.filter(x=>x.category==="EXCAVATOR")),
   api(path+"&activity=COAL&role=LOADING").then(rows=>rows.filter(x=>["EXCAVATOR","LOADER"].includes(x.category)))
 ]);
}
async function changeDate(){
 const dateField=h("srDate"), day=dateField.value;
 const [result,assets]=day?await Promise.all([
  fetchDrivers(day),fetchAssets(day).catch(()=>null)
 ]):[{rows:[],error:"Select an operating date"},[[],[],[],[]]];
 if(h("srDate")!==dateField||dateField.value!==day)return;
 model.drivers=result.rows;
 model.driverError=result.error;
 for(const select of document.querySelectorAll("[data-sr-driver]")){
  const current=select.value;
  select.innerHTML=driverOptions(result.error||model.drivers.some(x=>x.id===current)?current:"");
  refreshSearchDropdown(select);
 }
 if(assets){
  [model.masters.vehicles,model.masters.vehiclesOb,model.masters.excavators,model.masters.loadingCoal]=assets;
 }
 for(const select of document.querySelectorAll("[data-sr-asset]")){
  const items=assets?model.masters[select.dataset.srAsset]:[];
  const current=select.value;
  select.innerHTML=retainedOptions(items,!assets||items.some(x=>x.id===current)?current:"",
   assets?"Select from Masters":"Equipment Master could not be loaded");
  refreshSearchDropdown(select);
 }
 await Promise.all([history(),loadSummary(),window.KOCPQueue?.refresh?.(),loadMeterAssets(),loadMeterRows()]);
}
function existing(line,key){return String(line?.[key]??"")}
function blank(){return model.kind==="COAL"?{vehicleId:"",driverId:"",excavatorId:"",tripCount:"",routeId:""}:
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
 model.masters={COAL:a[0],OB:a[1],vehicles:a[2][0],vehiclesOb:a[2][1],excavators:a[2][2],loadingCoal:a[2][3],
               materials:a[3],codes:a[4],locations:a[6]};
 model.drivers=a[5].rows;
 model.driverError=a[5].error;
}
function h(id){return document.getElementById(id)}
function val(id){return h(id)?.value||""}
function availableShifts(){return (state.ctx?.shifts||[]).filter(x=>x.active!==false).map(x=>({id:x.shift,label:x.shift+" | "+(x.start||"")+"–"+(x.end||"")}))}
function lineHtml(line,i){
 if(model.kind==="COAL")return '<tr class="sr-row" data-no="'+i+'"><td>'+(i+1)+'</td>'+
 '<td><select data-sr-asset="vehicles" aria-label="Vehicle" id="srVehicle'+i+'">'+vehicleOptions("COAL",existing(line,"vehicleId"))+'</select></td>'+
 '<td><select data-sr-asset="loadingCoal" aria-label="Coal loader or excavator" id="srCoalLoader'+i+'">'+retainedOptions(model.masters.loadingCoal,existing(line,"excavatorId"),"Select loader / excavator")+'</select></td>'+ 
  '<td>'+driverSelect("srDriver"+i,existing(line,"driverId"))+'</td>'+
 '<td><input class="sr-numeric" aria-label="Trips" id="srCount'+i+'" type="number" min="1" max="200" step="1" value="'+esc(existing(line,"tripCount"))+'" oninput="KOCPSR.updateTotal()"></td>'+
 '<td><select aria-label="Route / Lead" id="srLineRoute'+i+'">'+routeOptions("COAL",existing(line,"routeId"))+'</select></td>'+
 '<td><button class="sr-small" type="button" onclick="KOCPSR.removeRow('+i+')">Remove</button></td></tr>';
 const patch=pointValue(line,"patchCode","sourceLocationId");
 const point=pointValue(line,"pointCode","destinationLocationId");
 return '<tr class="sr-row" data-no="'+i+'"><td>'+(i+1)+'</td>'+
 '<td><select data-sr-asset="excavators" aria-label="Excavator" id="srExcavator'+i+'" onchange="KOCPSR.updateTotal()">'+retainedOptions(model.masters.excavators,existing(line,"excavatorId"),"Select excavator")+'</select></td>'+
 '<td><select id="srPatch'+i+'" aria-label="Loading patch" onchange="KOCPSR.changePoints('+i+')">'+
 locationOptions("PATCH",patch)+'</select></td>'+
 '<td><select id="srPoint'+i+'" aria-label="Unloading point" onchange="KOCPSR.changePoints('+i+')">'+
 locationOptions("UNLOAD_POINT",point)+'</select></td>'+
 '<td><select aria-label="Route / Lead" id="srLineRoute'+i+'">'+
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
 refreshSearchDropdown(select);
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
 '<label class="sr-field"><span>Driver (optional)</span>'+driverSelect("srHeaderDriver",c.driverId||"")+'</label>':
 selectBox("srRelay","Relay",codeOptions("RELAY",c.relayCode||"")))+
 paperInput("srDeclared",c.declaredTotal??"","Paper trip total","number",'min="0" step="1"')+
 '</div><details class="sr-card-details" '+(ob?'open':'')+'><summary>'+(ob?'Tipper HMR / KMR & paper reference':'Paper reference & route')+'</summary><div class="sr-head">'+
 paperInput("srRef",c.sourceRef,"Paper reference")+
 selectBox("srRoute","Default route / lead",routeOptions(model.kind,c.routeId||""))+
 (ob?paperInput("srHmrOpen",c.openingHmr,"Opening HMR","number",'min="0" step="0.01"')+
 paperInput("srHmrClose",c.closingHmr,"Closing HMR","number",'min="0" step="0.01"')+
 paperInput("srKmrOpen",c.openingKmr,"Opening KMR","number",'min="0" step="0.1"')+
 paperInput("srKmrClose",c.closingKmr,"Closing KMR","number",'min="0" step="0.1"'):"")+
 '</div></details>';
}

function meterPanel(){
 return '<details class="sr-card sr-meter-card" open><summary>Equipment HMR / KMR — Excavator, Loader, Tipper</summary>'+
 '<p class="sr-muted">Select a Loader / Excavator against each Coal tipper row above, then enter that machine\&#39;s HMR once per shift below. OB tipper meters on paper cards post on verification; do not enter those twice.</p>'+
 '<div class="sr-meter-grid"><label class="sr-field"><span>Equipment Master</span>'+
 '<select id="srMeterAsset"><option value="">Loading assigned equipment…</option></select></label>'+
 '<label class="sr-field"><span>Meter</span><select id="srMeterType"><option value="HMR">HMR</option><option value="KMR">KMR</option></select></label>'+
 paperInput("srMeterOpen","","Opening","number",'min="0" step="0.001"')+
 paperInput("srMeterClose","","Closing","number",'min="0" step="0.001"')+
 paperInput("srMeterRemarks","","Remarks")+
 '<button class="sr-btn" type="button" onclick="KOCPSR.saveMeter()">Save meter</button></div>'+
 '<div id="srMeterMessage" role="status"></div><div id="srMeterRows" class="sr-muted">Loading existing readings…</div></details>';
}
async function loadMeterAssets(){
 const target=h("srMeterAsset"),day=val("srDate")||state.ctx?.operatingDate;if(!target||!day)return;
 try{
  const assets=await api("/api/site-ops/KOCP/lookups?kind=ASSET&limit=250&operating_date="+enc(day));
  if(h("srMeterAsset")!==target)return;
  target.innerHTML=retainedOptions(assets,assets.some(x=>x.id===target.value)?target.value:"",
   "Select assigned equipment by door / machine ID");
  refreshSearchDropdown(target);
 }catch(e){target.innerHTML='<option value="">Equipment Master not available</option>';refreshSearchDropdown(target)}
}
async function loadMeterRows(){
 const box=h("srMeterRows"),day=val("srDate"),shift=val("srShift");
 if(!box||!day||!shift)return [];
 try{
  const rows=await api("/api/site-ops/KOCP/meters?operating_date="+enc(day)+"&shift="+enc(shift));
  if(h("srMeterRows")!==box)return [];
  box.innerHTML=rows.length?
   '<div class="sr-scroll"><table class="sr-grid"><thead><tr><th>Equipment</th><th>Meter</th><th>Opening</th><th>Closing</th><th>Usage</th></tr></thead><tbody>'+
   rows.slice(0,20).map(x=>'<tr><td>'+esc(x.assetId)+'</td><td>'+esc(x.meterType)+'</td><td>'+
    esc(x.opening??"—")+'</td><td>'+esc(x.closing??"—")+'</td><td>'+esc(x.usage??"—")+'</td></tr>').join("")+
   '</tbody></table></div><small>'+rows.length+' readings found. All can be exported in Reports.</small>':
   'No readings for this date/shift.';
  return rows;
 }catch(e){box.textContent="Cannot load meter readings: "+e.message;return []}
}
async function saveMeter(){
 const out=h("srMeterMessage"),el=h("srMeterAsset");
 const day=val("srDate"),shift=val("srShift"),assetId=val("srMeterAsset"),kind=val("srMeterType");
 const opening=val("srMeterOpen"),closing=val("srMeterClose");
 try{
  const chosen=el?.selectedOptions?.[0]?.value?el.selectedOptions[0].textContent:"";
  const search=el?.closest(".sr-combo")?.querySelector(".sr-combo-input")?.value;
  if(!day||!shift||!assetId||!["HMR","KMR"].includes(kind)||search!==chosen)
   throw Error("Select a date, shift, equipment from Masters and meter type.");
  if(opening===""||closing===""||!Number.isFinite(Number(opening))||!Number.isFinite(Number(closing))||
     Number(opening)<0||Number(closing)<Number(opening))
   throw Error("Closing reading must not be lower than opening; both are required.");
  const existing=await api("/api/site-ops/KOCP/meters?operating_date="+enc(day)+"&shift="+enc(shift));
  if(existing.some(x=>x.assetId===assetId&&x.meterType===kind))
   throw Error("Reading already exists for this equipment, shift and type. No overwrite made.");
  await api("/api/site-ops/KOCP/meters",{
   method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify({operatingDate:day,shift,assetId,meterType:kind,openingReading:Number(opening),
     closingReading:Number(closing),sourceType:"PORTAL",remarks:val("srMeterRemarks")||null})});
  out.className="sr-success";out.textContent="Saved to Equipment Meter Register. Usage: "+(Number(closing)-Number(opening)).toFixed(3);
  h("srMeterOpen").value="";h("srMeterClose").value="";h("srMeterRemarks").value="";
  await loadMeterRows();
 }catch(e){if(out){out.className="sr-error";out.textContent=e.message}}
}

function screen(){
 const ob=model.kind==="OB",card=model.card,status=card?.status||"NEW";
 const lines=card?.lines?.length?card.lines:model.lines;
 const total=lines.reduce((sum,line)=>sum+Number(line.tripCount||0),0);
 return '<section class="sr-workbench"><div class="sr-heading"><div><h1>Shift Production Register</h1>'+
 '</div>'+
 '<div class="sr-badge">Status: '+esc(status)+'</div></div>'+
 '<div class="sr-tabs" role="group" aria-label="Register type"><button type="button" class="'+(ob?'':'active')+'" onclick="KOCPSR.switchKind(\'COAL\')">Coal Register</button>'+
 '<button type="button" class="'+(ob?'active':'')+'" onclick="KOCPSR.switchKind(\'OB\')">OB Trip Cards</button></div>'+
 '<div class="sr-card"><h2>'+(ob?'Tipper Card':'Coal Shift Sheet')+'</h2>'+
 headerHtml()+'</div>'+
 '<div class="sr-card"><div class="sr-toolbar"><h2>'+(ob?'OB Trip Counts':'Coal Vehicle/Driver Rows')+'</h2>'+
 '<div class="sr-entry-actions"><strong>Trips: <span id="srTotal">'+total+'</span></strong>'+
 '<button class="sr-small" type="button" onclick="KOCPSR.addRow()">Add row</button>'+
 '<button class="sr-small" type="button" onclick="KOCPSR.copyDown()">Copy down</button></div></div>'+
 '<div class="sr-scroll sr-entry-scroll" tabindex="0" aria-label="Trip entry rows"><table class="sr-grid"><thead><tr>'+(ob?
 '<th>#</th><th>Excavator</th><th>Patch</th><th>Unloading Point</th><th>Route / Lead</th><th class="sr-trip-column">Trips</th><th>Action</th>':
 '<th>#</th><th>Tipper</th><th>Loader / Excavator</th><th>Driver (optional)</th><th class="sr-trip-column">Trips</th><th>Route / Lead (override)</th><th>Action</th>')+
 '</tr></thead><tbody id="srRows">'+lines.map((x,i)=>lineHtml(x,i)).join("")+'</tbody></table></div>'+
 '</div>'+
 meterPanel()+
 '<div class="sr-card sr-action-card">'+
 '<div class="sr-actions"><button class="sr-btn sr-secondary" type="button" onclick="KOCPSR.save()">Save Draft</button>'+
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
  if(model.kind==="COAL"){r.vehicleId=val("srVehicle"+i);r.excavatorId=val("srCoalLoader"+i);r.driverId=val("srDriver"+i);r.tripCount=val("srCount"+i)}
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
async function renderSelf(){await fetchMasters();const w=h("workspace");if(w){w.innerHTML=screen();enhanceSearchDropdowns(w);await Promise.all([history(),loadSummary(),window.KOCPQueue?.refresh?.(),loadMeterAssets(),loadMeterRows()])}}
async function save(silent=false){
 try{
  validateSearchDropdowns();
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
 '<button class="sr-small" type="button" onclick="KOCPSR.open(\''+esc(x.cardId)+'\')">'+(["DRAFT","REJECTED"].includes(x.status)?"Edit":"View")+'</button> '+
   (["DRAFT","REJECTED"].includes(x.status)?'<button class="sr-small sr-danger" type="button" onclick="KOCPSR.cancel(\''+esc(x.cardId)+'\')">Delete</button>':'<small>Locked</small>')+'</td></tr>').join("")+
 '</tbody></table></div>';
 }catch(e){const out=h("srHistory");if(out)out.textContent=e.message}
}
async function open(id){try{const r=await api(PREFIX+"/cards/"+enc(id));model.kind=r.kind;model.card=r;model.lines=r.lines;model.clientKey=r.cardId;await renderSelf()}catch(e){notice(e.message,true)}}
async function cancelCard(id){
 try{
  const card=await api(PREFIX+"/cards/"+enc(id));
  if(!["DRAFT","REJECTED"].includes(card.status))
    throw Error("Only Draft or Returned registers can be deleted. Verified production requires authorized correction.");
  const reason=window.prompt("Reason for deleting this "+card.kind+" register (at least 5 characters):");
  if(reason===null)return;
  if(reason.trim().length<5)throw Error("Enter a deletion reason of at least 5 characters.");
  if(!window.confirm("Delete this unverified register? Its audit history will be retained."))return;
  await api(PREFIX+"/cards/"+enc(id)+"/cancel",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({expectedVersion:card.version,reason:reason.trim()})});
  if(model.card?.cardId===id)fresh(model.kind==="COAL"?4:2);
  await renderSelf();notice("Register deleted from active entries; audit record retained.");
 }catch(e){notice(e.message,true)}
}
function updateTotal(){
 const el=h("srTotal");if(!el)return;
 el.textContent=[...document.querySelectorAll("#srRows .sr-numeric")]
  .reduce((sum,input)=>sum+(Number(input.value)||0),0);
}
function redrawRows(focusIndex){
 h("srRows").innerHTML=model.lines.map(lineHtml).join("");
 enhanceSearchDropdowns(h("srRows"));
 updateTotal();
 if(focusIndex!==undefined){
  h((model.kind==="OB"?"srExcavator":"srVehicle")+focusIndex)?.closest(".sr-combo")?.querySelector(".sr-combo-input")?.focus();
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
window.KOCPSR={save:()=>save().catch(()=>{}),submit,verify,reject,history,open,cancel:cancelCard,updateTotal,addRow,removeRow,
 copyDown,switchKind,newCard,renderCodeMasters,editCode,saveCode,changeDate,changePoints,loadMeterRows,saveMeter,afterRender:async()=>{enhanceSearchDropdowns(h("workspace"));await Promise.all([history(),loadSummary(),window.KOCPQueue?.refresh?.(),loadMeterAssets(),loadMeterRows()])}};
})();

