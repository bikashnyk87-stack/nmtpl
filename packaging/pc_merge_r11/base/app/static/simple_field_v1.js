/* NMTPL v1.0 RC3 - Hard Simple Field Operations UX
   Keeps the full backend, but field workflows are select -> enter -> save.
*/
(function(){
const baseRender = render;
const baseRenderWB = typeof renderWB12==='function'?renderWB12:(typeof renderWB==='function'?renderWB:null);
const baseRenderHSD = typeof renderHsdV12==='function'?renderHsdV12:(typeof renderHSD==='function'?renderHSD:null);
const SIMPLE={
  SOCP:{daily:['TRIP','WB','HSD'],review:['RECONCILIATION','DATA_QUALITY'],control:['FLEET','LOADER','DRIVER','GP_DESTINATION','REPORTS','MASTERS','MAP','SATELLITE','AUDIT']},
  KOCP:{daily:['TRIP','OB','HSD','HMR_KMR'],review:['RECONCILIATION','MCL_FACTOR','MCL_SURVEY','BILLING','DATA_QUALITY'],control:['FLEET','LOADER','EXCAVATOR','REPORTS','MASTERS','MAP','SATELLITE','AUDIT']}
};
const MGMT=['FLEET','LOADER','EXCAVATOR','DRIVER','GP_DESTINATION','GPS','DATA_QUALITY','MAP','SATELLITE','MASTERS','AUDIT'];
const label={PRODUCTION:'Production Entry',TRIP:'Trip Entry',OB:'OB Entry',WB:'Weighbridge',HSD:'Fuel / HSD',MECHANICAL:'Mechanical',HMR_KMR:'Machine Meter',MIS:'Paper Report Review',RECONCILIATION:'Check & Match',REPORTS:'Reports',MCL_FACTOR:'MCL Quantity Rules',MCL_SURVEY:'MCL Certified Quantity',BILLING:'Billing Check'};
function isMgmt(){return !!state.bootstrap?.user?.isManagement}
function authorised(m){return (state.ctx?.modules||[]).includes(m)}
function simpleShift(){
  const allowed=(state.ctx?.shifts||[]).filter(x=>['A','B','C'].includes(String(x.shift).toUpperCase()));
  if(allowed.some(x=>x.shift===state.ctx?.shift)) return state.ctx.shift;
  const now=new Date(),mins=now.getHours()*60+now.getMinutes();
  for(const s of allowed){const [sh,sm]=String(s.start).split(':').map(Number),[eh,em]=String(s.end).split(':').map(Number);const a=sh*60+sm,b=eh*60+em;if((a<b&&mins>=a&&mins<b)||(a>b&&(mins>=a||mins<b)))return s.shift}
  return allowed[0]?.shift||'A';
}
function shiftOpts(selected){return (state.ctx?.shifts||[]).filter(x=>['A','B','C'].includes(String(x.shift).toUpperCase())).map(s=>`<option value="${esc(s.shift)}" ${s.shift===selected?'selected':''}>${esc(s.shift)} · ${esc(s.start)}–${esc(s.end)}</option>`).join('')}
function uuid(){return (crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random().toString(16).slice(2)}`).replace(/[^A-Za-z0-9-]/g,'')}
function dtLocal(d=new Date()){const x=new Date(d.getTime()-d.getTimezoneOffset()*60000);return x.toISOString().slice(0,16)}
function simpleUser(){return NMTPLNet.safeUser(state.bootstrap?.user?.loginId||state.bootstrap?.user?.name||'anonymous')}
function simpleDate(){return state.ctx?.operatingDate||new Date().toISOString().slice(0,10)}
function draftKey(module){return `NMTPL_SIMPLE_DRAFT:${siteId}:${simpleUser()}:${simpleDate()}:${module}`}
function stablePayload(o){if(Array.isArray(o))return `[${o.map(stablePayload).join(',')}]`;if(o&&typeof o==='object')return `{${Object.keys(o).sort().filter(k=>k!=='requestId').map(k=>JSON.stringify(k)+':'+stablePayload(o[k])).join(',')}}`;return JSON.stringify(o??null)}
function fastHash(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return (h>>>0).toString(16).padStart(8,'0')}
function reqKey(module,slot='single'){return `NMTPL_SIMPLE_REQ:${siteId}:${simpleUser()}:${simpleDate()}:${module}:${slot}`}
function getReq(module,payload={},slot='single'){const key=reqKey(module,slot),fp=fastHash(stablePayload(payload));let saved=null;try{saved=JSON.parse(localStorage.getItem(key)||'null')}catch{};if(!saved||saved.fingerprint!==fp||!saved.requestId){saved={fingerprint:fp,requestId:`WEB-${siteId}-${module}-${fp}-${uuid().slice(0,12)}`};localStorage.setItem(key,JSON.stringify(saved))}return saved.requestId}
function clearReq(module,slot=null){if(slot!==null){localStorage.removeItem(reqKey(module,slot));return}const prefix=`NMTPL_SIMPLE_REQ:${siteId}:${simpleUser()}:${simpleDate()}:${module}:`;const keys=[];for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i)||'';if(k.startsWith(prefix))keys.push(k)}keys.forEach(k=>localStorage.removeItem(k))}
function saveDraft(containerId,key){const root=$(containerId);if(!root)return;const o={};root.querySelectorAll('input[id],select[id],textarea[id]').forEach(el=>{if(el.type!=='file')o[el.id]=el.type==='checkbox'?el.checked:el.value});localStorage.setItem(key,JSON.stringify(o));const x=root.querySelector('.draft-state');if(x){x.textContent='Draft saved ✓';x.classList.add('ok')}}
function restoreDraft(containerId,key){const root=$(containerId);if(!root)return;let o={};try{o=JSON.parse(localStorage.getItem(key)||'{}')}catch{};Object.entries(o).forEach(([id,v])=>{const el=$(id);if(el){if(el.type==='checkbox')el.checked=!!v;else el.value=v}});root.querySelectorAll('input,select,textarea').forEach(el=>{if(el.type==='file'||el.dataset.noDraft)return;el.addEventListener('input',()=>saveDraft(containerId,key));el.addEventListener('change',()=>saveDraft(containerId,key))})}
function clearDraft(containerId,key){localStorage.removeItem(key);const root=$(containerId),x=root?.querySelector('.draft-state');if(x){x.textContent='Saved';x.classList.add('ok')}}
function lookupMarkup(hiddenId,kind,placeholder,groups=''){
  return `<div class="lookup" data-kind="${kind}" data-hidden="${hiddenId}" data-groups="${groups}"><input id="${hiddenId}Text" type="text" autocomplete="off" placeholder="${esc(placeholder)}"><input id="${hiddenId}" type="hidden"><div class="lookup-menu"></div></div>`
}
function itemAllowed(w,item){const g=(w.dataset.groups||'').split(',').map(x=>x.trim().toUpperCase()).filter(Boolean);if(!g.length)return true;const hay=`${item.group||''} ${item.type||''}`.toUpperCase();return g.some(x=>hay.includes(x))}
function bindLookups(root=document){root.querySelectorAll('.lookup:not([data-bound])').forEach(w=>{w.dataset.bound='1';const input=w.querySelector('input[type=text]'),hidden=w.querySelector('input[type=hidden]'),menu=w.querySelector('.lookup-menu');let timer=null,items=[],active=-1;
  async function search(){const q=input.value.trim();menu.innerHTML='<div class="lookup-empty">Searching…</div>';w.classList.add('open');try{let data=await api(`/api/site-ops/${siteId}/lookups?kind=${encodeURIComponent(w.dataset.kind)}&q=${encodeURIComponent(q)}&limit=40`);data=(data||[]).filter(x=>itemAllowed(w,x));items=data;active=-1;menu.innerHTML=data.length?data.map((x,i)=>`<div class="lookup-item" data-i="${i}"><b>${esc(x.label)}</b><small>${esc(x.sub||x.id)}</small></div>`).join(''):'<div class="lookup-empty">No matching active master record</div>';menu.querySelectorAll('.lookup-item').forEach(el=>el.onclick=()=>choose(items[+el.dataset.i]))}catch(e){menu.innerHTML=`<div class="lookup-empty">${esc(e.message)}</div>`}}
  function choose(x){hidden.value=x.id;input.value=x.label;input.dataset.selected=x.id;input.dataset.vehicleNo=x.vehicleNo||'';input.dataset.doorNo=x.doorNo||'';w.classList.remove('open');input.dispatchEvent(new Event('change',{bubbles:true}))}
  input.addEventListener('focus',search);input.addEventListener('input',()=>{hidden.value='';input.dataset.selected='';clearTimeout(timer);timer=setTimeout(search,160)});input.addEventListener('keydown',e=>{if(!w.classList.contains('open'))return;if(e.key==='ArrowDown'){e.preventDefault();active=Math.min(active+1,items.length-1)}else if(e.key==='ArrowUp'){e.preventDefault();active=Math.max(active-1,0)}else if(e.key==='Enter'&&active>=0){e.preventDefault();choose(items[active])}else if(e.key==='Escape'){w.classList.remove('open')}else return;menu.querySelectorAll('.lookup-item').forEach((el,i)=>el.classList.toggle('active',i===active))})
})}
document.addEventListener('click',e=>{document.querySelectorAll('.lookup.open').forEach(w=>{if(!w.contains(e.target))w.classList.remove('open')})});
function simplePageHead(title,desc){return `<div class="software-page-head"><div><h1>${esc(title)}</h1><p>${esc(desc)}</p></div><div class="software-page-meta"><b>${siteId}</b><span>${esc(state.ctx.operatingDate)}</span><span>Shift ${esc(simpleShift())}</span></div></div>`}
function setSimpleNav(){
  const cfg=SIMPLE[siteId]||{daily:[],review:[],control:[]};
  const available=new Set(state.ctx?.modules||[]);
  const groups=[
    ['OPERATIONS',['DASHBOARD',...cfg.daily]],
    ['REVIEW',cfg.review||[]],
    ['CONTROL',cfg.control||[]],
  ];
  const n=$('sideNav');
  n.innerHTML=groups.map(([title,mods])=>{
    const rows=[...new Set(mods)].filter(m=>m==='DASHBOARD'||available.has(m));
    if(!rows.length)return '';
    return `<div class="field-nav-section">${title}</div>`+rows.map(m=>{
      const x=META[m]||['--',m,''];
      const text=m==='DASHBOARD'?'Dashboard':(label[m]||x[1]);
      return `<button class="field-nav-btn ${state.module===m?'active':''}" data-module="${m}"><span>${x[0]}</span><b>${esc(text)}</b></button>`;
    }).join('');
  }).join('');
  n.querySelectorAll('[data-module]').forEach(b=>b.onclick=()=>{state.module=b.dataset.module;simpleRender()});
}
setNav=setSimpleNav;window.setNav=setSimpleNav;
function taskCards(mods){return `<div class="task-cards">${mods.filter(authorised).map(m=>{const x=META[m]||['--',m,''];const action=m==='MECHANICAL'?(siteId==='TIOM'?`location.href='/tiom'`:`location.href='/site/${siteId}'`):`setModule('${m}')`;return `<button class="task-card" onclick="${action}"><span class="task-icon">${x[0]}</span><div><b>${esc(label[m]||x[1])}</b><small>${esc(x[2])}</small></div><strong>Open →</strong></button>`}).join('')}</div>`}
function renderSimpleDashboard(){
  const cfg=SIMPLE[siteId]||{daily:[],review:[],control:[]};
  const d=state.dash||{};
  const draftCount=cfg.daily.filter(m=>localStorage.getItem(draftKey(m))).length;
  const siteTitle=siteId==='SOCP'?'SOCP Operations Dashboard':'KOCP Operations Dashboard';
  const siteDesc=siteId==='SOCP'?'Trips, weighbridge, fuel and daily operating controls.':'Coal, OB, MCL quantity controls, fuel and equipment operations.';
  const reviewCards=(cfg.review||[]).filter(authorised);
  const controlCards=(cfg.control||[]).filter(m=>authorised(m)&&['REPORTS','MASTERS','FLEET','DATA_QUALITY'].includes(m));
  return `<div class="field-home simple-home software-home">
    ${pageHead(siteTitle,siteDesc)}
    <div class="simple-daybar"><div><small>OPERATING DATE</small><b>${esc(state.ctx.operatingDate)}</b></div><div><small>CURRENT SHIFT</small><b>${esc(simpleShift())}</b></div><div><small>DRAFTS ON THIS PC</small><b>${draftCount}</b></div></div>
    <div class="simple-kpis software-kpis">
      <div><small>TRIPS TODAY</small><b>${fmt(d.trips||0)}</b></div>
      <div><small>${siteId==='KOCP'?'COAL / MT':'QUANTITY MT'}</small><b>${fmt(d.quantityMt||0,2)}</b></div>
      <div><small>${siteId==='KOCP'?'OB CuM':'WB ROWS'}</small><b>${siteId==='KOCP'?fmt(d.quantityCum||0,2):fmt(d.wbRows||0)}</b></div>
      <div><small>HSD ISSUED</small><b>${fmt(d.hsdIssuedL||0,1)} L</b></div>
    </div>
    <div class="software-section"><div class="simple-start-title"><h2>Daily Operations</h2><p>Master-driven entry. Search by vehicle number, door number or machine name.</p></div>${taskCards(cfg.daily)}</div>
    ${reviewCards.length?`<div class="software-section"><div class="simple-start-title"><h2>Review & Control</h2><p>Check exceptions and approved quantities before reporting.</p></div>${taskCards(reviewCards)}</div>`:''}
    ${controlCards.length?`<div class="software-section"><div class="simple-start-title"><h2>Management</h2><p>Reports, master data and fleet controls.</p></div>${taskCards(controlCards)}</div>`:''}
    <div class="simple-help-box"><b>ERP rule</b><span>Select from the master search. Internal IDs and categories are handled by the system.</span></div>
  </div>`;
}
renderDashboard=renderSimpleDashboard;window.renderDashboard=renderSimpleDashboard;

async function renderTiomProduction(){const [acts,recent]=await Promise.all([api('/api/site-ops/TIOM/lookups?kind=ACTIVITY&limit=100').catch(()=>[]),api(`/api/site-ops/TIOM/production/simple?operating_date=${state.ctx.operatingDate}&limit=40`).catch(()=>[])]);const rows=recent.map(r=>`<tr><td>${esc(r.shift)}</td><td>${esc(r.machineId)}</td><td>${esc(r.vehicleId||'—')}</td><td>${esc(r.sourceLocationId)}</td><td>${esc(r.destinationLocationId||'—')}</td><td>${esc(r.materialId||'—')}</td><td>${esc(r.loadingAt||'—')}</td><td>${esc(r.unloadingAt||'—')}</td><td>${esc(r.status)}</td></tr>`);const now=dtLocal();return simplePageHead('TIOM Production Entry','Simple completed-trip entry. Attendance and Shift Management are not required for this screen.')+`<div id="tiomSimpleForm" class="simple-form"><div class="simple-entry-grid"><div class="field"><span>Operating Date *</span><input id="spDate" type="date" data-no-draft value="${state.ctx.operatingDate}"></div><div class="field"><span>Shift *</span><select id="spShift">${shiftOpts(simpleShift())}</select></div><div class="field"><span>Loading Time *</span><input id="spLoad" type="datetime-local" value="${now}"></div><div class="field"><span>Unloading Time *</span><input id="spUnload" type="datetime-local"></div><div class="field"><span>Loader / Excavator *</span>${lookupMarkup('spMachine','ASSET','Search loader / excavator','LOADING,LOADER,EXCAVATOR')}</div><div class="field"><span>Vehicle *</span>${lookupMarkup('spVehicle','ASSET','Search registration / door','TRANSPORT,VEHICLE,TIPPER,DUMPER')}</div><div class="field"><span>Source *</span>${lookupMarkup('spSource','LOCATION','Search source')}</div><div class="field"><span>Destination *</span>${lookupMarkup('spDest','LOCATION','Search destination')}</div><div class="field"><span>Material *</span>${lookupMarkup('spMaterial','MATERIAL','Search material')}</div><div class="field"><span>Activity *</span><select id="spActivity">${acts.map(x=>`<option value="${esc(x.id)}" ${String(x.id).toUpperCase()==='LOADING'?'selected':''}>${esc(x.label)}</option>`).join('')}</select></div></div><div class="simple-actions"><button id="spSave" class="btn primary" onclick="saveTiomSimpleProduction()">Save Production Entry</button><button class="btn outline" onclick="clearTiomSimpleDraft()">Clear</button><span class="draft-state">Draft autosaves on this PC</span></div><div class="simple-note">WB remains the authoritative source for production tonnes. This field record supplies vehicle/loader/route/timing evidence for matching.</div></div>${panel('Today’s Entries',recentTable(['Shift','Loader','Vehicle','Source','Destination','Material','Loading','Unloading','Status'],rows),`${recent.length} recent records`)}`}
async function saveTiomSimpleProduction(){const btn=$('spSave');try{for(const id of ['spMachine','spVehicle','spSource','spDest','spMaterial'])if(!$(id).value)throw new Error(`Choose a valid ${id.replace('sp','').toLowerCase()} from search`);if(!$('spUnload').value)throw new Error('Enter unloading time');btn.disabled=true;const body={operatingDate:$('spDate').value,shift:$('spShift').value,loadingAt:$('spLoad').value,unloadingAt:$('spUnload').value,machineId:$('spMachine').value,vehicleId:$('spVehicle').value,sourceLocationId:$('spSource').value,destinationLocationId:$('spDest').value,materialId:$('spMaterial').value,activity:$('spActivity').value};body.requestId=getReq('PRODUCTION',body,'single');const r=await api('/api/site-ops/TIOM/production/simple',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});clearDraft('tiomSimpleForm',draftKey('PRODUCTION'));clearReq('PRODUCTION');toast(r.idempotent?'Entry already saved — no duplicate created':'Production entry saved');await render()}catch(e){toast(e.message,'bad')}finally{if(btn)btn.disabled=false}}
function clearTiomSimpleDraft(){localStorage.removeItem(draftKey('PRODUCTION'));clearReq('PRODUCTION');render()}

function tripGridRows(kind,count=5){const isSocp=siteId==='SOCP';return Array.from({length:count},(_,i)=>`<tr class="simple-trip-row" data-i="${i}"><td>${i+1}</td><td><select class="stShift">${shiftOpts(simpleShift())}</select></td><td>${lookupMarkup(`stVehicle${i}`,'ASSET','Vehicle','TRANSPORT,VEHICLE,TIPPER,DUMPER')}</td><td>${lookupMarkup(`stLoader${i}`,'ASSET',siteId==='KOCP'?'Loader / Excavator':'Loader','LOADING,LOADER,EXCAVATOR')}</td>${isSocp?`<td>${lookupMarkup(`stDest${i}`,'LOCATION','Unloading point')}</td>`:`<td>${lookupMarkup(`stMaterial${i}`,'MATERIAL','Material')}</td>`}<td><input class="stGp" id="stGp${i}" placeholder="GP / ref"></td><td>${isSocp?`<input class="stQty qty" id="stQty${i}" type="number" inputmode="decimal" min="0" step="0.001" placeholder="MT">`:'<span class="simple-status muted">Auto by MCL rule</span>'}</td><td><span id="stStatus${i}" class="simple-status muted">Ready</span></td></tr>`).join('')}
async function renderSimpleTrips(kind='TRIP'){const title=siteId==='KOCP'?(kind==='OB'?'KOCP OB Entry':'KOCP Coal Entry'):'SOCP Trip Entry';const desc=siteId==='SOCP'?'Fast daily entry using vehicle, loader, shift, unloading point and quantity.':kind==='OB'?'OB CuM is applied automatically from the approved MCL rule.':'Coal MT per trip is applied automatically from the approved MCL shift rule.';const rec=await api(`/api/sites/${siteId}/records/trips?operating_date=${state.ctx.operatingDate}&limit=40`).catch(()=>[]);const rows=rec.map(r=>`<tr><td>${esc(r.shift)}</td><td>${esc(r.vehicleId||r.vehicleRaw||'—')}</td><td>${esc(r.loadingEquipmentId||'—')}</td><td>${esc(siteId==='SOCP'?r.destinationLocationId:r.materialId||'—')}</td><td>${esc(r.gpNo||'—')}</td><td>${fmt(r.quantityMt,3)}</td><td>${fmt(r.quantityCum,3)}</td><td>${esc(r.weightBasis||'—')}</td></tr>`);return simplePageHead(title,desc)+`<div id="simpleTripForm" class="simple-form"><div class="simple-top"><div class="field"><span>Entry Date</span><input id="stDate" type="date" data-no-draft value="${state.ctx.operatingDate}"></div><div class="field"><span>Default Shift</span><select id="stDefaultShift" onchange="applyTripDefaults()">${shiftOpts(simpleShift())}</select></div><div class="field"><span>Rows</span><select id="stRows" onchange="rebuildSimpleTripRows()"><option>5</option><option selected>10</option><option>20</option><option>30</option></select></div></div><div class="simple-table-wrap"><table class="simple-grid-table"><thead><tr><th>#</th><th>Shift</th><th>Vehicle</th><th>${siteId==='KOCP'?'Loader / Excavator':'Loader'}</th><th>${siteId==='SOCP'?'Unloading Point':'Material'}</th><th>GP / Ref</th><th>${siteId==='SOCP'?'Qty MT':'Quantity'}</th><th>Status</th></tr></thead><tbody id="simpleTripRows">${tripGridRows(kind,10)}</tbody></table></div><div class="simple-actions"><button id="stSave" class="btn primary" onclick="saveSimpleTrips('${kind}')">Save Entered Rows</button><button class="btn outline" onclick="clearSimpleTripDraft()">Clear</button><span class="draft-state">Draft autosaves on this PC</span></div></div>${panel('Today’s Entries',recentTable(['Shift','Vehicle','Loader/Excavator',siteId==='SOCP'?'Destination':'Material','GP','MT','CuM','Basis'],rows),`${rec.length} recent records`)}`}
function rebuildSimpleTripRows(){const n=+$('stRows').value||5;$('simpleTripRows').innerHTML=tripGridRows(state.module==='OB'?'OB':'TRIP',n);bindLookups($('simpleTripForm'));restoreDraft('simpleTripForm',draftKey(state.module));}
function applyTripDefaults(){document.querySelectorAll('.stShift').forEach(x=>x.value=$('stDefaultShift').value);saveDraft('simpleTripForm',draftKey(state.module))}
async function saveSimpleTrips(kind){const btn=$('stSave'),rows=[...document.querySelectorAll('.simple-trip-row')];let used=0,done=0;btn.disabled=true;try{for(const row of rows){const i=row.dataset.i,vehicle=$(`stVehicle${i}`).value,loader=$(`stLoader${i}`).value,detail=siteId==='SOCP'?$(`stDest${i}`).value:$(`stMaterial${i}`).value,gp=$(`stGp${i}`).value.trim(),qty=siteId==='SOCP'?$(`stQty${i}`).value:'';if(!vehicle&&!loader&&!detail&&!gp&&!qty)continue;used++;const st=$(`stStatus${i}`);try{if(!vehicle)throw new Error('Select vehicle');if(!loader)throw new Error('Select loader/excavator');if(!detail)throw new Error(siteId==='SOCP'?'Select unloading point':'Select material');if(siteId==='SOCP'&&!qty)throw new Error('Enter MT');st.textContent='Saving…';st.className='simple-status muted';const body={kind,operatingDate:$('stDate').value,shift:row.querySelector('.stShift').value,vehicleId:vehicle,loadingEquipmentId:loader,gpNo:gp||null};if(siteId==='SOCP'){body.destinationLocationId=detail;body.quantityMt=qty}else body.materialId=detail;body.requestId=getReq(kind,body,i);const r=await api(`/api/site-ops/${siteId}/trips/simple`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});st.textContent=r.idempotent?'Already saved':'Saved ✓';st.className='simple-status good';clearReq(kind,i);done++}catch(e){st.textContent=e.message;st.className='simple-status bad'}}if(!used)throw new Error('Enter at least one row');if(done===used){clearDraft('simpleTripForm',draftKey(kind));clearReq(kind);toast(`${done} row${done===1?'':'s'} saved`);setTimeout(()=>render(),500)}else toast(`${done}/${used} rows saved. Correct the red rows.`,done?'good':'bad')}catch(e){toast(e.message,'bad')}finally{btn.disabled=false}}
function clearSimpleTripDraft(){localStorage.removeItem(draftKey(state.module));clearReq(state.module);render()}


function wbGridRows(count=10){
  const now=dtLocal();
  return Array.from({length:count},(_,i)=>`<tr class="simple-wb-row" data-i="${i}">
    <td>${i+1}</td>
    <td><input id="swbId${i}" class="wb-id" placeholder="WB ID"></td>
    <td><input id="swbTime${i}" class="wb-time" type="datetime-local" value="${now}"></td>
    <td>${lookupMarkup(`swbVehicle${i}`,'ASSET','Vehicle','TRANSPORT,VEHICLE,TIPPER,DUMPER')}</td>
    <td>${lookupMarkup(`swbSource${i}`,'LOCATION','Source')}</td>
    <td>${lookupMarkup(`swbDest${i}`,'LOCATION','Destination')}</td>
    <td><input id="swbGross${i}" class="wb-gross" type="number" min="0" inputmode="decimal" oninput="simpleCalcWbRow(${i})"></td>
    <td><input id="swbTare${i}" class="wb-tare" type="number" min="0" inputmode="decimal" oninput="simpleCalcWbRow(${i})"></td>
    <td><input id="swbNet${i}" class="simple-readonly wb-net" readonly></td>
    <td><span id="swbStatus${i}" class="simple-status muted">Ready</span></td>
  </tr>`).join('')
}
async function renderSimpleWB(){
  const data=await api(`/api/sites/${siteId}/records/wb?operating_date=${state.ctx.operatingDate}&limit=60`).catch(()=>[]);
  const rows=data.map(r=>`<tr><td>${esc(r.wbId)}</td><td>${esc(r.weighAt)}</td><td>${esc(r.shift)}</td><td>${esc(r.vehicle)}</td><td>${esc(r.source||'—')}</td><td>${esc(r.destination||'—')}</td><td>${fmt((r.netKg||0)/1000,3)}</td><td>${esc(r.status)}</td></tr>`);
  return simplePageHead(`${siteId} Weighbridge`,'Enter multiple WB rows together. Net weight is calculated automatically.')+
  `<div id="simpleWbForm" class="simple-form batch-entry-form">
    <div class="simple-top compact-entry-controls">
      <div class="field"><span>Default Party</span><input id="swbParty" value="NMTPL"></div>
      <div class="field"><span>Rows</span><select id="swbRows" onchange="rebuildSimpleWbRows()"><option>5</option><option selected>10</option><option>20</option><option>30</option></select></div>
      <div class="batch-hint"><b>One Save = all entered rows</b><span>Blank rows are ignored. Errors stay on the affected row.</span></div>
    </div>
    <div class="simple-table-wrap">
      <table class="simple-grid-table software-entry-grid wb-entry-grid">
        <thead><tr><th>#</th><th>WB ID</th><th>Weigh Time</th><th>Vehicle</th><th>Source</th><th>Destination</th><th>Gross kg</th><th>Tare kg</th><th>Net kg</th><th>Status</th></tr></thead>
        <tbody id="simpleWbRows">${wbGridRows(10)}</tbody>
      </table>
    </div>
    <div class="simple-actions"><button id="swbSave" class="btn primary" onclick="saveSimpleWB()">Save Entered WB Rows</button><button class="btn outline" onclick="clearSimpleWbDraft()">Clear</button><span class="draft-state">Draft autosaves on this PC</span></div>
    ${isMgmt()?`<details class="simple-advanced"><summary>Excel bulk upload</summary><div class="toolbar" style="margin-top:8px"><button class="btn outline" onclick="location.href='/api/site-ops/${siteId}/wb/template.xlsx'">Download Template</button><input id="wbImportFile" type="file" accept=".xlsx"><button class="btn outline" onclick="previewWbImport()">Preview Upload</button></div><div id="wbImportPreview"></div></details>`:''}
  </div>`+
  panel('Today’s WB Records',recentTable(['WB ID','Time','Shift','Vehicle','Source','Destination','Net MT','Status'],rows),`${data.length} recent records`);
}
function rebuildSimpleWbRows(){
  const n=+$('swbRows').value||10;
  $('simpleWbRows').innerHTML=wbGridRows(n);
  bindLookups($('simpleWbForm'));
  restoreDraft('simpleWbForm',draftKey('WB'));
}
function simpleCalcWbRow(i){
  const g=Number($(`swbGross${i}`)?.value),t=Number($(`swbTare${i}`)?.value),n=$(`swbNet${i}`),st=$(`swbStatus${i}`);
  if(!n)return;
  if(!Number.isFinite(g)||!Number.isFinite(t)||g<=0||t<0){n.value='';if(st&&!st.classList.contains('good')){st.textContent='Ready';st.className='simple-status muted'};return}
  if(g<=t){n.value='';st.textContent='Gross ≤ Tare';st.className='simple-status bad';return}
  n.value=(g-t).toFixed(0);
  if(!st.classList.contains('good')){st.textContent=((g-t)/1000).toFixed(3)+' MT';st.className='simple-status info'}
  saveDraft('simpleWbForm',draftKey('WB'));
}
async function saveSimpleWB(){
  const btn=$('swbSave'),rows=[...document.querySelectorAll('.simple-wb-row')];
  let used=0,done=0;btn.disabled=true;
  try{
    for(const row of rows){
      const i=row.dataset.i,id=$(`swbId${i}`).value.trim(),vehicle=$(`swbVehicle${i}`).value,g=$(`swbGross${i}`).value,t=$(`swbTare${i}`).value;
      const source=$(`swbSource${i}`).value,dest=$(`swbDest${i}`).value,time=$(`swbTime${i}`).value,st=$(`swbStatus${i}`);
      if(!id&&!vehicle&&!g&&!t&&!source&&!dest)continue;
      used++;
      try{
        simpleCalcWbRow(i);
        if(!id)throw new Error('WB ID required');
        if(!time)throw new Error('Time required');
        if(!vehicle)throw new Error('Select vehicle');
        if(!$('swbNet'+i).value)throw new Error('Check weights');
        const vin=$(`swbVehicle${i}Text`);
        const body={wbId:id,weighAt:time,vehicleRegNo:vin.dataset.vehicleNo||vin.value,party:$('swbParty').value.trim()||null,source:$('swbSource'+i+'Text').value.trim()||null,destination:$('swbDest'+i+'Text').value.trim()||null,grossKg:g,tareKg:t,netKg:$('swbNet'+i).value};
        st.textContent='Saving…';st.className='simple-status muted';
        await api(`/api/sites/${siteId}/wb/manual`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        st.textContent='Saved ✓';st.className='simple-status good';done++;
      }catch(e){st.textContent=e.message;st.className='simple-status bad'}
    }
    if(!used)throw new Error('Enter at least one WB row');
    if(done===used){localStorage.removeItem(draftKey('WB'));toast(`${done} WB row${done===1?'':'s'} saved`);setTimeout(()=>render(),500)}
    else toast(`${done}/${used} WB rows saved. Correct the red rows.`,done?'good':'bad');
  }catch(e){toast(e.message,'bad')}finally{btn.disabled=false}
}
function clearSimpleWbDraft(){localStorage.removeItem(draftKey('WB'));render()}

function hsdGridRows(count=10){
  return Array.from({length:count},(_,i)=>`<tr class="simple-hsd-row" data-i="${i}">
    <td>${i+1}</td>
    <td><select id="shShift${i}">${shiftOpts(simpleShift())}</select></td>
    <td><select id="shType${i}" onchange="toggleHsdRow(${i})"><option value="ISSUE">Issue</option><option value="RECEIPT">Receipt</option></select></td>
    <td><div id="shAssetBox${i}">${lookupMarkup(`shAsset${i}`,'ASSET','Equipment')}</div><input id="shSupplier${i}" class="hsd-supplier" placeholder="Supplier" style="display:none"></td>
    <td><input id="shLitres${i}" type="number" min="0" step="0.001" inputmode="decimal" placeholder="Litres"></td>
    <td><input id="shRef${i}" placeholder="Slip / challan / ref"></td>
    <td><span id="shStatus${i}" class="simple-status muted">Ready</span></td>
  </tr>`).join('')
}
async function renderSimpleHsd(){
  const data=await api(`/api/sites/${siteId}/records/hsd?limit=60`).catch(()=>[]);
  const rows=data.map(r=>`<tr><td>${esc(r.operatingDate)}</td><td>${esc(r.shift||'—')}</td><td>${esc(r.transactionType)}</td><td>${esc(r.assetId||'—')}</td><td>${fmt(r.litres,2)}</td><td>${esc(r.referenceNo||'—')}</td><td>${esc(r.status)}</td></tr>`);
  return simplePageHead(`${siteId} Fuel / HSD`,'Enter multiple equipment issues or stock receipts in one batch.')+
  `<div id="simpleHsdForm" class="simple-form batch-entry-form">
    <div class="simple-top compact-entry-controls">
      <div class="field"><span>Date *</span><input id="shDate" type="date" data-no-draft value="${state.ctx.operatingDate}"></div>
      <div class="field"><span>Rows</span><select id="shRows" onchange="rebuildSimpleHsdRows()"><option>5</option><option selected>10</option><option>20</option><option>30</option></select></div>
      <div class="batch-hint"><b>Fast HSD entry</b><span>Use one row per equipment issue / receipt. Blank rows are ignored.</span></div>
    </div>
    <div class="simple-table-wrap"><table class="simple-grid-table software-entry-grid hsd-entry-grid">
      <thead><tr><th>#</th><th>Shift</th><th>Type</th><th>Equipment / Supplier</th><th>Litres</th><th>Reference</th><th>Status</th></tr></thead>
      <tbody id="simpleHsdRows">${hsdGridRows(10)}</tbody>
    </table></div>
    <div class="simple-actions"><button id="shSave" class="btn primary" onclick="saveSimpleHsd()">Save Entered HSD Rows</button><button class="btn outline" onclick="clearSimpleHsdDraft()">Clear</button><span class="draft-state">Draft autosaves on this PC</span></div>
  </div>`+
  panel('Recent HSD',recentTable(['Date','Shift','Type','Asset','Litres','Reference','Status'],rows),`${data.length} recent records`);
}
function toggleHsdRow(i){
  const receipt=$(`shType${i}`)?.value==='RECEIPT',asset=$(`shAssetBox${i}`),supplier=$(`shSupplier${i}`);
  if(asset)asset.style.display=receipt?'none':'';
  if(supplier)supplier.style.display=receipt?'':'none';
}
function rebuildSimpleHsdRows(){
  const n=+$('shRows').value||10;$('simpleHsdRows').innerHTML=hsdGridRows(n);bindLookups($('simpleHsdForm'));restoreDraft('simpleHsdForm',draftKey('HSD'));
  for(let i=0;i<n;i++)toggleHsdRow(i);
}
async function saveSimpleHsd(){
  const btn=$('shSave'),rows=[...document.querySelectorAll('.simple-hsd-row')];let used=0,done=0;btn.disabled=true;
  try{
    for(const row of rows){
      const i=row.dataset.i,type=$(`shType${i}`).value,asset=$(`shAsset${i}`).value,litres=$(`shLitres${i}`).value,supplier=$(`shSupplier${i}`).value.trim(),ref=$(`shRef${i}`).value.trim(),st=$(`shStatus${i}`);
      if(!asset&&!litres&&!supplier&&!ref)continue;
      used++;
      try{
        if(type==='ISSUE'&&!asset)throw new Error('Select equipment');
        if(type==='RECEIPT'&&!supplier)throw new Error('Enter supplier');
        if(!+litres)throw new Error('Enter litres');
        const body={operatingDate:$('shDate').value,shift:$(`shShift${i}`).value,transactionType:type,assetType:type==='ISSUE'?'EQUIPMENT':null,assetId:type==='ISSUE'?asset:null,litres,supplier:type==='RECEIPT'?supplier:null,referenceNo:ref||null,sourceType:'PORTAL'};
        st.textContent='Saving…';st.className='simple-status muted';
        await api(`/api/sites/${siteId}/hsd`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        st.textContent='Saved ✓';st.className='simple-status good';done++;
      }catch(e){st.textContent=e.message;st.className='simple-status bad'}
    }
    if(!used)throw new Error('Enter at least one HSD row');
    if(done===used){localStorage.removeItem(draftKey('HSD'));toast(`${done} HSD row${done===1?'':'s'} saved`);setTimeout(()=>render(),500)}
    else toast(`${done}/${used} HSD rows saved. Correct the red rows.`,done?'good':'bad');
  }catch(e){toast(e.message,'bad')}finally{btn.disabled=false}
}
function clearSimpleHsdDraft(){localStorage.removeItem(draftKey('HSD'));render()}


function meterGridRows(count=10){
  return Array.from({length:count},(_,i)=>`<tr class="simple-meter-row" data-i="${i}">
    <td>${i+1}</td>
    <td><select id="smShift${i}">${shiftOpts(simpleShift())}</select></td>
    <td>${lookupMarkup(`smAsset${i}`,'ASSET','Machine / vehicle')}</td>
    <td><select id="smType${i}"><option>HMR</option><option>KMR</option><option>OTHER</option></select></td>
    <td><input id="smOpen${i}" type="number" step="0.01" oninput="calcMeterRow(${i})"></td>
    <td><input id="smClose${i}" type="number" step="0.01" oninput="calcMeterRow(${i})"></td>
    <td><input id="smUse${i}" class="simple-readonly" readonly></td>
    <td><input id="smRemarks${i}" placeholder="Remarks"></td>
    <td><span id="smStatus${i}" class="simple-status muted">Ready</span></td>
  </tr>`).join('')
}
async function renderSimpleMeter(){
  const rows=await api(`/api/site-ops/${siteId}/meters?operating_date=${state.ctx.operatingDate}`).catch(()=>[]);
  const tr=rows.map(r=>`<tr><td>${esc(r.shift)}</td><td>${esc(r.assetId)}</td><td>${esc(r.meterType)}</td><td>${r.opening??'—'}</td><td>${r.closing??'—'}</td><td>${r.usage??'—'}</td><td>${esc(r.remarks||'—')}</td></tr>`);
  return simplePageHead('HMR / KMR','Enter meter readings for multiple machines in one batch.')+
  `<div id="simpleMeterForm" class="simple-form batch-entry-form">
    <div class="simple-top compact-entry-controls">
      <div class="field"><span>Date *</span><input id="smDate" type="date" data-no-draft value="${state.ctx.operatingDate}"></div>
      <div class="field"><span>Rows</span><select id="smRows" onchange="rebuildSimpleMeterRows()"><option>5</option><option selected>10</option><option>20</option><option>30</option></select></div>
      <div class="batch-hint"><b>Shift meter sheet</b><span>Enter all machine readings together; usage is calculated automatically.</span></div>
    </div>
    <div class="simple-table-wrap"><table class="simple-grid-table software-entry-grid meter-entry-grid">
      <thead><tr><th>#</th><th>Shift</th><th>Machine / Vehicle</th><th>Meter</th><th>Opening</th><th>Closing</th><th>Usage</th><th>Remarks</th><th>Status</th></tr></thead>
      <tbody id="simpleMeterRows">${meterGridRows(10)}</tbody>
    </table></div>
    <div class="simple-actions"><button id="smSave" class="btn primary" onclick="saveSimpleMeters()">Save Entered Readings</button><button class="btn outline" onclick="clearSimpleMeterDraft()">Clear</button><span class="draft-state">Draft autosaves on this PC</span></div>
  </div>`+panel('Meter Register',recentTable(['Shift','Asset','Type','Opening','Closing','Usage','Remarks'],tr),`${rows.length} readings`);
}
function calcMeterRow(i){
  const a=Number($(`smOpen${i}`)?.value),b=Number($(`smClose${i}`)?.value),u=$(`smUse${i}`),st=$(`smStatus${i}`);
  if(!u)return;if(!Number.isFinite(a)||!Number.isFinite(b)){u.value='';return}
  if(b<a){u.value='';st.textContent='Closing < Opening';st.className='simple-status bad';return}
  u.value=(b-a).toFixed(2);if(!st.classList.contains('good')){st.textContent='Ready';st.className='simple-status info'}
}
function rebuildSimpleMeterRows(){
  const n=+$('smRows').value||10;$('simpleMeterRows').innerHTML=meterGridRows(n);bindLookups($('simpleMeterForm'));restoreDraft('simpleMeterForm',draftKey('HMR_KMR'));
}
async function saveSimpleMeters(){
  const btn=$('smSave'),rows=[...document.querySelectorAll('.simple-meter-row')];let used=0,done=0;btn.disabled=true;
  try{
    for(const row of rows){
      const i=row.dataset.i,asset=$(`smAsset${i}`).value,opening=$(`smOpen${i}`).value,closing=$(`smClose${i}`).value,remarks=$(`smRemarks${i}`).value.trim(),st=$(`smStatus${i}`);
      if(!asset&&!opening&&!closing&&!remarks)continue;used++;
      try{
        if(!asset)throw new Error('Select machine');
        if(opening===''||closing==='')throw new Error('Enter both readings');
        calcMeterRow(i);if(!$('smUse'+i).value&&Number(closing)!==Number(opening))throw new Error('Check readings');
        const body={operatingDate:$('smDate').value,shift:$(`smShift${i}`).value,assetId:asset,meterType:$(`smType${i}`).value,openingReading:opening,closingReading:closing,remarks:remarks||null,sourceType:'PORTAL'};
        st.textContent='Saving…';st.className='simple-status muted';
        await api(`/api/site-ops/${siteId}/meters`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        st.textContent='Saved ✓';st.className='simple-status good';done++;
      }catch(e){st.textContent=e.message;st.className='simple-status bad'}
    }
    if(!used)throw new Error('Enter at least one meter row');
    if(done===used){localStorage.removeItem(draftKey('HMR_KMR'));toast(`${done} meter row${done===1?'':'s'} saved`);setTimeout(()=>render(),500)}
    else toast(`${done}/${used} readings saved. Correct the red rows.`,done?'good':'bad');
  }catch(e){toast(e.message,'bad')}finally{btn.disabled=false}
}
function clearSimpleMeterDraft(){localStorage.removeItem(draftKey('HMR_KMR'));render()}
window.NMTPLClearActiveDrafts=function(){NMTPLNet.clearUserDrafts(simpleUser())};
function afterSimpleRender(){bindLookups($('workspace'));if(state.module==='PRODUCTION')restoreDraft('tiomSimpleForm',draftKey('PRODUCTION'));if(['TRIP','OB'].includes(state.module))restoreDraft('simpleTripForm',draftKey(state.module));if(state.module==='WB'){restoreDraft('simpleWbForm',draftKey('WB'));document.querySelectorAll('.simple-wb-row').forEach(r=>simpleCalcWbRow(r.dataset.i))}if(state.module==='HSD'){restoreDraft('simpleHsdForm',draftKey('HSD'));document.querySelectorAll('.simple-hsd-row').forEach(r=>toggleHsdRow(r.dataset.i))}if(state.module==='HMR_KMR'){restoreDraft('simpleMeterForm',draftKey('HMR_KMR'));document.querySelectorAll('.simple-meter-row').forEach(r=>calcMeterRow(r.dataset.i))}const f=document.querySelector('.sidebar-foot b');if(f)f.textContent='v1.0 RC3 · Simple Field UX';if($('centralBtn'))$('centralBtn').style.display=isMgmt()?'':'none';if(!isMgmt()&&$('siteSwitcher')){const c=[...$('siteSwitcher').options].find(o=>o.value==='CENTRAL');if(c)c.remove()}}
async function simpleRender(){
  const cfg=SIMPLE[siteId]||{daily:[],review:[],control:[]};
  const visible=new Set(['DASHBOARD',...(cfg.daily||[]),...(cfg.review||[]),...(cfg.control||[])]);
  if(!visible.has(state.module) || (state.module!=='DASHBOARD'&&!authorised(state.module))){
    state.module='DASHBOARD';
  }
  setSimpleNav();
  const a=META[state.module]||['--',state.module,''];
  $('crumbTop').textContent=`NMTPL / ${siteId}`;
  $('crumbTitle').textContent=state.module==='DASHBOARD'?'Operations Dashboard':(label[state.module]||a[1]);
  let html=null;
  if(state.module==='DASHBOARD') html=renderSimpleDashboard();
  else if(['TRIP','OB'].includes(state.module)) html=await renderSimpleTrips(state.module);
  else if(state.module==='WB') html=await renderSimpleWB();
  else if(state.module==='HSD') html=await renderSimpleHsd();
  else if(state.module==='HMR_KMR') html=await renderSimpleMeter();
  else {
    await baseRender();
    setSimpleNav();
    return;
  }
  if(html!==null && typeof html==='string') $('workspace').innerHTML=html;
  afterSimpleRender();
}
render=simpleRender;window.render=simpleRender;
Object.assign(window,{saveTiomSimpleProduction,clearTiomSimpleDraft,rebuildSimpleTripRows,applyTripDefaults,saveSimpleTrips,clearSimpleTripDraft,rebuildSimpleWbRows,simpleCalcWbRow,saveSimpleWB,clearSimpleWbDraft,rebuildSimpleHsdRows,toggleHsdRow,saveSimpleHsd,clearSimpleHsdDraft,rebuildSimpleMeterRows,calcMeterRow,saveSimpleMeters,clearSimpleMeterDraft});
(function activateHardSimpleMode(attempt){
  if(state.ctx && state.bootstrap){
    simpleRender().catch(e=>{console.error('Simple UX init',e);toast(e.message||'Unable to open Simple Field Mode','bad')});
    return;
  }
  if((attempt||0)<50) setTimeout(()=>activateHardSimpleMode((attempt||0)+1),100);
})(0);
})();
