/* NMTPL v1.0 RC3 - Hard Simple Field Operations UX
   Keeps the full backend, but field workflows are select -> enter -> save.
*/
(function(){
const baseRender = render;
const baseRenderWB = typeof renderWB12==='function'?renderWB12:(typeof renderWB==='function'?renderWB:null);
const baseRenderHSD = typeof renderHsdV12==='function'?renderHsdV12:(typeof renderHSD==='function'?renderHSD:null);
const SIMPLE={
  SOCP:{entry:['TRIP','WB','HSD'],setup:['ATTENDANCE','SHIFT_CONTROL'],review:['RECONCILIATION','DATA_QUALITY'],control:['FLEET','LOADER','DRIVER','GP_DESTINATION','REPORTS','MASTERS','MAP','SATELLITE','AUDIT']},
  KOCP:{entry:['TRIP','OB','HSD','HMR_KMR'],setup:['ATTENDANCE','SHIFT_CONTROL'],review:['RECONCILIATION','MCL_FACTOR','MCL_SURVEY','BILLING','DATA_QUALITY'],control:['FLEET','LOADER','EXCAVATOR','REPORTS','MASTERS','MAP','SATELLITE','AUDIT']}
};
const MGMT=['FLEET','LOADER','EXCAVATOR','DRIVER','GP_DESTINATION','GPS','DATA_QUALITY','MAP','SATELLITE','MASTERS','AUDIT'];
const label={DASHBOARD:'Dashboard',ATTENDANCE:'Attendance Entry',SHIFT_CONTROL:'Shift Setup',PRODUCTION:'Production Entry',TRIP:'Trip Entry',OB:'OB Entry',WB:'Weighbridge Entry',HSD:'Fuel / HSD Entry',MECHANICAL:'Mechanical',HMR_KMR:'HMR / KMR Entry',MIS:'Paper Report Review',RECONCILIATION:'Check & Match',REPORTS:'Reports',MCL_FACTOR:'MCL Quantity Rules',MCL_SURVEY:'MCL Certified Quantity',BILLING:'Billing Check'};
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
  const cfg=SIMPLE[siteId]||{entry:[],setup:[],review:[],control:[]};
  const available=new Set(state.ctx?.modules||[]);
  const groups=[
    ['DATA ENTRY',['DASHBOARD',...(cfg.entry||[])]],
    ['SHIFT SETUP',cfg.setup||[]],
    ['REVIEW',cfg.review||[]],
    ['CONTROL',cfg.control||[]],
  ];
  const n=$('sideNav');
  n.innerHTML=groups.map(([title,mods])=>{
    const rows=[...new Set(mods)].filter(m=>m==='DASHBOARD'||available.has(m));
    if(!rows.length)return '';
    return `<div class="field-nav-section">${title}</div>`+rows.map(m=>{
      const x=META[m]||['--',m,''];
      const text=m==='DASHBOARD'?'Entry Console':(label[m]||x[1]);
      return `<button class="field-nav-btn ${state.module===m?'active':''}" data-module="${m}"><span>${x[0]}</span><b>${esc(text)}</b></button>`;
    }).join('');
  }).join('');
  n.querySelectorAll('[data-module]').forEach(b=>b.onclick=()=>{state.module=b.dataset.module;simpleRender()});
}
setNav=setSimpleNav;window.setNav=setSimpleNav;
function taskCards(mods){return `<div class="task-cards">${mods.filter(authorised).map(m=>{const x=META[m]||['--',m,''];const action=m==='MECHANICAL'?(siteId==='TIOM'?`location.href='/tiom'`:`location.href='/site/${siteId}'`):`setModule('${m}')`;return `<button class="task-card" onclick="${action}"><span class="task-icon">${x[0]}</span><div><b>${esc(label[m]||x[1])}</b><small>${esc(x[2])}</small></div><strong>Open →</strong></button>`}).join('')}</div>`}
function entryFlowCards(mods,startNo=1){
  return `<div class="entry-flow-grid">${mods.filter(authorised).map((m,i)=>{
    const x=META[m]||['--',m,''];
    return `<button class="entry-flow-card" onclick="setModule('${m}')">
      <span class="entry-step">${startNo+i}</span>
      <span class="entry-flow-icon">${x[0]}</span>
      <span class="entry-flow-copy"><b>${esc(label[m]||x[1])}</b><small>${esc(x[2]||'Open entry sheet')}</small></span>
      <strong>Open →</strong>
    </button>`;
  }).join('')}</div>`
}

function dashNum(v,d=0){return Number(v||0).toLocaleString('en-IN',{minimumFractionDigits:0,maximumFractionDigits:d})}
function dashKpi(label,value,note='',tone=''){
  return `<div class="ops-kpi ${tone}"><span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(note)}</small></div>`;
}
function dashBars(rows,key,unit='',limit=7){
  const data=(rows||[]).slice(0,limit),max=Math.max(0,...data.map(x=>Number(x[key]||0)));
  if(!data.length)return '<div class="ops-empty">No data for this period.</div>';
  return `<div class="ops-bars">${data.map((x,i)=>{const v=Number(x[key]||0),w=max>0?Math.max(3,(v/max)*100):0;return `<div class="ops-bar-row"><div class="ops-bar-label"><b>${esc(x.label||x.id||'—')}</b><span>${dashNum(v,key==='trips'?0:2)}${unit}</span></div><div class="ops-bar-track"><i style="width:${w}%"></i></div><small>${dashNum(x.trips||0)} trips</small></div>`}).join('')}</div>`;
}
function dashTrend(rows,key,label,unit=''){
  const data=rows||[],vals=data.map(x=>Number(x[key]||0)),max=Math.max(1,...vals);
  if(!data.length)return '<div class="ops-empty">No trend data.</div>';
  const W=520,H=148,p=14,n=Math.max(1,data.length-1);
  const pts=data.map((x,i)=>{const px=p+(i/n)*(W-p*2),py=H-p-(Number(x[key]||0)/max)*(H-p*2);return [px,py]}).map(a=>a.join(',')).join(' ');
  const first=data[0]?.date||'',last=data[data.length-1]?.date||'';
  return `<div class="ops-line"><div class="ops-chart-head"><b>${esc(label)}</b><span>Peak ${dashNum(max,key==='trips'?0:2)}${unit}</span></div><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-label="${esc(label)}"><line x1="${p}" y1="${H-p}" x2="${W-p}" y2="${H-p}" class="axis"></line><polyline points="${pts}" class="trend"></polyline>${data.map((x,i)=>{if(data.length>20&&i%Math.ceil(data.length/10)!==0&&i!==data.length-1)return'';const a=pts.split(' ')[i].split(',');return `<circle cx="${a[0]}" cy="${a[1]}" r="2.5"><title>${esc(x.date)}: ${dashNum(x[key]||0,key==='trips'?0:2)}${unit}</title></circle>`}).join('')}</svg><div class="ops-axis-labels"><span>${esc(first)}</span><span>${esc(last)}</span></div></div>`;
}
function dashDonut(status){
  const entries=Object.entries(status||{}).filter(([,v])=>Number(v)>0),total=entries.reduce((a,[,v])=>a+Number(v),0);
  if(!total)return '<div class="ops-empty">Fleet status not updated today.</div>';
  const colors=['#08766d','#3c90a8','#d39a28','#b94b4b','#6d7f86','#7f66a8'];
  let acc=0,stops=[];
  entries.forEach(([k,v],i)=>{const a=acc,b=acc+(Number(v)/total)*100;stops.push(`${colors[i%colors.length]} ${a}% ${b}%`);acc=b});
  return `<div class="ops-donut-wrap"><div class="ops-donut" style="background:conic-gradient(${stops.join(',')})"><div><b>${total}</b><span>Assets</span></div></div><div class="ops-legend">${entries.map(([k,v],i)=>`<div><i style="background:${colors[i%colors.length]}"></i><span>${esc(k.replaceAll('_',' '))}</span><b>${v}</b></div>`).join('')}</div></div>`;
}
function dashShiftCards(rows,site){
  if(!(rows||[]).length)return '<div class="ops-empty">No shift data.</div>';
  return `<div class="ops-shifts">${rows.map(x=>`<div><strong>Shift ${esc(x.shift)}</strong><b>${dashNum(x.trips)} trips</b><span>${site==='KOCP'?`${dashNum(x.quantityMt,1)} MT · ${dashNum(x.quantityCum,1)} CuM`:`${dashNum(x.quantityMt,1)} MT`}</span><small>HSD ${dashNum(x.hsdL,1)} L</small></div>`).join('')}</div>`;
}
function dashQuickActions(cfg){
  const mods=(cfg.entry||[]).filter(authorised);
  return `<div class="ops-quick">${mods.map(m=>{const a=META[m]||['↗',label[m]||m,''];return `<button onclick="openSiteModule('${m}')"><span>${a[0]}</span><b>${esc(label[m]||a[1])}</b><small>Open entry</small></button>`}).join('')}</div>`;
}
window.openSiteModule=function(m){if(authorised(m)){state.module=m;render()}};
window.applySiteDashRange=function(){window.__siteDashFrom=$('opsFrom')?.value||null;window.__siteDashTo=$('opsTo')?.value||null;render()};
async function renderSimpleDashboard(){
  const cfg=SIMPLE[siteId]||{entry:[],setup:[],review:[],control:[]};
  const today=state.ctx.operatingDate;
  const defFrom=String(today).slice(0,8)+'01';
  const from=window.__siteDashFrom||defFrom,to=window.__siteDashTo||today;
  const d=await api(`/api/site-ops/${siteId}/dashboard/operations?from_date=${encodeURIComponent(from)}&to_date=${encodeURIComponent(to)}`).catch(e=>({error:e.message,todayTotals:{},periodTotals:{},shifts:[],trend:[],materials:[],destinations:[],vehicles:[],loaders:[],fleet:{status:{}},reconciliation:{},meters:{},factors:[]}));
  if(d.error)return `<div class="bad">${esc(d.error)}</div>`;
  const t=d.todayTotals||{},p=d.periodTotals||{},isK=siteId==='KOCP';
  const draftCount=(cfg.entry||[]).filter(m=>localStorage.getItem(draftKey(m))).length;
  const trendKey=isK?(p.quantityCum>p.quantityMt?'quantityCum':'quantityMt'):(p.wbMt>0?'wbMt':'quantityMt');
  // WB MT is not daily in trend; SOCP uses trip MT trend, while WB MT remains KPI.
  const trendMetric=isK?(p.quantityCum>p.quantityMt?'quantityCum':'quantityMt'):'quantityMt';
  const trendTitle=isK?(trendMetric==='quantityCum'?'OB CuM trend':'Coal MT trend'):'Production MT trend';
  const trendUnit=trendMetric==='quantityCum'?' CuM':' MT';
  const materialKey=isK?(p.quantityCum>p.quantityMt?'quantityCum':'quantityMt'):'quantityMt';

  const kpis=isK?[
    dashKpi('Today Trips',dashNum(t.trips),'Current operating day','primary'),
    dashKpi('Coal / MT',dashNum(t.quantityMt,1),`Period ${dashNum(p.quantityMt,1)} MT`,'good'),
    dashKpi('OB / CuM',dashNum(t.quantityCum,1),`Period ${dashNum(p.quantityCum,1)} CuM`,'warn'),
    dashKpi('HSD Issued',dashNum(t.hsdIssuedL,1)+' L',p.lPerCum?`${dashNum(p.lPerCum,2)} L/CuM period`:'Period fuel',''),
    dashKpi('Fleet Updated',dashNum(Object.values(d.fleet?.status||{}).reduce((a,b)=>a+Number(b||0),0)),`${dashNum(d.fleet?.assigned||0)} assigned`,''),
    dashKpi('Open Exceptions',dashNum((d.openDataQuality||0)+(d.missingTripFieldsToday||0)),'Data quality / incomplete','bad')
  ]:[
    dashKpi('Today Trips',dashNum(t.trips),'Current operating day','primary'),
    dashKpi('Trip Qty',dashNum(t.quantityMt,1)+' MT',`Period ${dashNum(p.quantityMt,1)} MT`,'good'),
    dashKpi('WB Qty',dashNum(t.wbMt,1)+' MT',`${dashNum(t.wbRows)} WB rows today`,'good'),
    dashKpi('HSD Issued',dashNum(t.hsdIssuedL,1)+' L',p.lPerMt?`${dashNum(p.lPerMt,2)} L/MT period`:'Period fuel',''),
    dashKpi('Vehicles Used',dashNum(t.vehicles),`${dashNum(d.fleet?.assigned||0)} assigned`,''),
    dashKpi('Open Exceptions',dashNum((d.openDataQuality||0)+(d.missingTripFieldsToday||0)),'Data quality / incomplete','bad')
  ];

  const recon=Object.entries(d.reconciliation||{});
  const reconHtml=recon.length?`<div class="ops-mini-stats">${recon.map(([k,v])=>`<div><span>${esc(k.replaceAll('_',' '))}</span><b>${v}</b></div>`).join('')}</div>`:'<div class="ops-empty">No reconciliation records in this period.</div>';
  const factorHtml=isK?(d.factors||[]).length?`<div class="ops-factor-grid">${d.factors.map(x=>`<div><span>${esc(x.type.replaceAll('_',' '))}</span><b>${dashNum(x.value,3)} ${esc(x.unit)}</b><small>Shift ${esc(x.shift)}${x.reference?' · '+esc(x.reference):''}</small></div>`).join('')}</div>`:'<div class="ops-empty">No approved MCL factor active today.</div>':'';

  const special=isK?`
    <section class="ops-panel ops-wide"><div class="ops-panel-head"><div><b>MCL / Billing Control</b><span>Approved operational conversion and latest certification status.</span></div><button onclick="openSiteModule('MCL_FACTOR')">Open MCL Rules</button></div>
      ${factorHtml}
      <div class="ops-cert-row">
        <div><span>Latest Survey</span><b>${d.latestSurvey?dashNum(d.latestSurvey.measuredCum,2)+' CuM':'—'}</b><small>${d.latestSurvey?esc(String(d.latestSurvey.periodEnd))+' · '+esc(d.latestSurvey.status):'No survey recorded'}</small></div>
        <div><span>Latest Billing Variance</span><b>${d.latestBilling&&d.latestBilling.varianceCum!=null?dashNum(d.latestBilling.varianceCum,2)+' CuM':'—'}</b><small>${d.latestBilling?esc(String(d.latestBilling.periodEnd))+' · '+esc(d.latestBilling.status):'No billing reconciliation'}</small></div>
        <div><span>Meter Usage</span><b>${dashNum(d.meters?.HMR||0,1)} H</b><small>${dashNum(d.meters?.KMR||0,1)} KM</small></div>
      </div>
    </section>`:`
    <section class="ops-panel ops-wide"><div class="ops-panel-head"><div><b>Weighbridge & Reconciliation</b><span>Period WB control and trip matching status.</span></div><button onclick="openSiteModule('RECONCILIATION')">Open Review</button></div>
      <div class="ops-cert-row">
        <div><span>WB Period</span><b>${dashNum(p.wbMt,1)} MT</b><small>${dashNum(p.wbRows)} valid rows</small></div>
        <div><span>Trip Period</span><b>${dashNum(p.quantityMt,1)} MT</b><small>${dashNum(p.trips)} trips</small></div>
        <div><span>Difference</span><b>${dashNum((p.wbMt||0)-(p.quantityMt||0),1)} MT</b><small>WB − trip entry</small></div>
      </div>${reconHtml}
    </section>`;

  return `<div class="ops-dashboard">
    <div class="ops-dashboard-top">
      <div><h1>${siteId} Operations Dashboard</h1><p>${isK?'Coal + OB operational control with MCL, equipment and fuel visibility.':'Dispatch + WB operational control with loader, destination, fleet and fuel visibility.'}</p></div>
      <div class="ops-range"><label>From<input id="opsFrom" type="date" value="${esc(from)}"></label><label>To<input id="opsTo" type="date" value="${esc(to)}"></label><button onclick="applySiteDashRange()">Apply</button></div>
    </div>

    <section class="ops-entry-strip"><div class="ops-strip-head"><div><b>Quick Entry</b><span>Field work stays one click away from the dashboard.</span></div><small>${draftCount} local draft sheet${draftCount===1?'':'s'}</small></div>${dashQuickActions(cfg)}</section>

    <div class="ops-kpis">${kpis.join('')}</div>

    <div class="ops-grid">
      <section class="ops-panel ops-trend"><div class="ops-panel-head"><div><b>${esc(trendTitle)}</b><span>${esc(from)} → ${esc(to)}</span></div></div>${dashTrend(d.trend,trendMetric,trendTitle,trendUnit)}</section>
      <section class="ops-panel"><div class="ops-panel-head"><div><b>Shift Performance</b><span>Trips, quantity and fuel by shift.</span></div></div>${dashShiftCards(d.shifts,siteId)}</section>

      <section class="ops-panel"><div class="ops-panel-head"><div><b>Material Mix</b><span>Highest movement materials.</span></div></div>${dashBars(d.materials,materialKey,materialKey==='quantityCum'?' CuM':' MT',7)}</section>
      <section class="ops-panel"><div class="ops-panel-head"><div><b>Destination Performance</b><span>Where material moved.</span></div></div>${dashBars(d.destinations,materialKey,materialKey==='quantityCum'?' CuM':' MT',8)}</section>

      <section class="ops-panel"><div class="ops-panel-head"><div><b>${isK?'Loader / Excavator':'Loader'} Productivity</b><span>Trips and handled quantity.</span></div></div>${dashBars(d.loaders,materialKey,materialKey==='quantityCum'?' CuM':' MT',8)}</section>
      <section class="ops-panel"><div class="ops-panel-head"><div><b>Vehicle Productivity</b><span>Top transport units by movement.</span></div></div>${dashBars(d.vehicles,'trips','',8)}</section>

      <section class="ops-panel"><div class="ops-panel-head"><div><b>Fleet Status — Today</b><span>Updated attendance/condition against assigned assets.</span></div></div>${dashDonut(d.fleet?.status||{})}</section>
      <section class="ops-panel"><div class="ops-panel-head"><div><b>Control Health</b><span>Entry completeness and reconciliation.</span></div><button onclick="openSiteModule('DATA_QUALITY')">Exceptions</button></div>
        <div class="ops-health">
          <div><span>Open DQ issues</span><b>${dashNum(d.openDataQuality||0)}</b></div>
          <div><span>Incomplete trips today</span><b>${dashNum(d.missingTripFieldsToday||0)}</b></div>
          <div><span>Assigned assets</span><b>${dashNum(d.fleet?.assigned||0)}</b></div>
          <div><span>Current shift</span><b>${esc(d.currentShift||simpleShift())}</b></div>
        </div>
        ${reconHtml}
      </section>

      ${special}
    </div>
  </div>`;
}

renderDashboard=renderSimpleDashboard;window.renderDashboard=renderSimpleDashboard;

async function renderTiomProduction(){const [acts,recent]=await Promise.all([api('/api/site-ops/TIOM/lookups?kind=ACTIVITY&limit=100').catch(()=>[]),api(`/api/site-ops/TIOM/production/simple?operating_date=${state.ctx.operatingDate}&limit=40`).catch(()=>[])]);const rows=recent.map(r=>`<tr><td>${esc(r.shift)}</td><td>${esc(r.machineId)}</td><td>${esc(r.vehicleId||'—')}</td><td>${esc(r.sourceLocationId)}</td><td>${esc(r.destinationLocationId||'—')}</td><td>${esc(r.materialId||'—')}</td><td>${esc(r.loadingAt||'—')}</td><td>${esc(r.unloadingAt||'—')}</td><td>${esc(r.status)}</td></tr>`);const now=dtLocal();return simplePageHead('TIOM Production Entry','Simple completed-trip entry. Attendance and Shift Management are not required for this screen.')+`<div id="tiomSimpleForm" class="simple-form"><div class="simple-entry-grid"><div class="field"><span>Operating Date *</span><input id="spDate" type="date" data-no-draft value="${state.ctx.operatingDate}"></div><div class="field"><span>Shift *</span><select id="spShift">${shiftOpts(simpleShift())}</select></div><div class="field"><span>Loading Time *</span><input id="spLoad" type="datetime-local" value="${now}"></div><div class="field"><span>Unloading Time *</span><input id="spUnload" type="datetime-local"></div><div class="field"><span>Loader / Excavator *</span>${lookupMarkup('spMachine','ASSET','Search loader / excavator','LOADING,LOADER,EXCAVATOR')}</div><div class="field"><span>Vehicle *</span>${lookupMarkup('spVehicle','ASSET','Search registration / door','TRANSPORT,VEHICLE,TIPPER,DUMPER')}</div><div class="field"><span>Source *</span>${lookupMarkup('spSource','LOCATION','Search source')}</div><div class="field"><span>Destination *</span>${lookupMarkup('spDest','LOCATION','Search destination')}</div><div class="field"><span>Material *</span>${lookupMarkup('spMaterial','MATERIAL','Search material')}</div><div class="field"><span>Activity *</span><select id="spActivity">${acts.map(x=>`<option value="${esc(x.id)}" ${String(x.id).toUpperCase()==='LOADING'?'selected':''}>${esc(x.label)}</option>`).join('')}</select></div></div><div class="simple-actions"><button id="spSave" class="btn primary" onclick="saveTiomSimpleProduction()">Save Production Entry</button><button class="btn outline" onclick="clearTiomSimpleDraft()">Clear</button><span class="draft-state">Draft autosaves on this PC</span></div><div class="simple-note">WB remains the authoritative source for production tonnes. This field record supplies vehicle/loader/route/timing evidence for matching.</div></div>${panel('Today’s Entries',recentTable(['Shift','Loader','Vehicle','Source','Destination','Material','Loading','Unloading','Status'],rows),`${recent.length} recent records`)}`}
async function saveTiomSimpleProduction(){const btn=$('spSave');try{for(const id of ['spMachine','spVehicle','spSource','spDest','spMaterial'])if(!$(id).value)throw new Error(`Choose a valid ${id.replace('sp','').toLowerCase()} from search`);if(!$('spUnload').value)throw new Error('Enter unloading time');btn.disabled=true;const body={operatingDate:$('spDate').value,shift:$('spShift').value,loadingAt:$('spLoad').value,unloadingAt:$('spUnload').value,machineId:$('spMachine').value,vehicleId:$('spVehicle').value,sourceLocationId:$('spSource').value,destinationLocationId:$('spDest').value,materialId:$('spMaterial').value,activity:$('spActivity').value};body.requestId=getReq('PRODUCTION',body,'single');const r=await api('/api/site-ops/TIOM/production/simple',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});clearDraft('tiomSimpleForm',draftKey('PRODUCTION'));clearReq('PRODUCTION');toast(r.idempotent?'Entry already saved — no duplicate created':'Production entry saved');await render()}catch(e){toast(e.message,'bad')}finally{if(btn)btn.disabled=false}}
function clearTiomSimpleDraft(){localStorage.removeItem(draftKey('PRODUCTION'));clearReq('PRODUCTION');render()}

function tripGridRows(kind,count=10){
  const isSocp=siteId==='SOCP';
  return Array.from({length:count},(_,i)=>`<tr class="simple-trip-row" data-i="${i}">
    <td>${i+1}</td>
    <td><select class="stShift">${shiftOpts(simpleShift())}</select></td>
    <td>${lookupMarkup(`stVehicle${i}`,'ASSET','Vehicle','TRANSPORT,VEHICLE,TIPPER,DUMPER')}</td>
    <td>${lookupMarkup(`stLoader${i}`,'ASSET',siteId==='KOCP'?'Loader / Excavator':'Loader','LOADING,LOADER,EXCAVATOR')}</td>
    ${isSocp
      ?`<td>${lookupMarkup(`stDest${i}`,'LOCATION','Unloading point')}</td>`
      :`<td>${lookupMarkup(`stSource${i}`,'LOCATION','Source')}</td><td>${lookupMarkup(`stDest${i}`,'LOCATION','Destination')}</td><td>${lookupMarkup(`stMaterial${i}`,'MATERIAL','Material')}</td>`}
    <td><input class="stGp" id="stGp${i}" placeholder="GP / ref"></td>
    <td>${isSocp?`<input class="stQty qty" id="stQty${i}" type="number" inputmode="decimal" min="0" step="0.001" placeholder="MT">`:'<span class="simple-status muted">Auto by MCL rule</span>'}</td>
    <td><span id="stStatus${i}" class="simple-status muted">Ready</span></td>
  </tr>`).join('')
}
function defaultLookupBox(id,label,groups=''){return `<div class="field"><span>${label}</span>${lookupMarkup(id,groups==='MATERIAL'?'MATERIAL':groups==='LOCATION'?'LOCATION':'ASSET','Search '+label,groups==='MATERIAL'||groups==='LOCATION'?'':groups)}</div>`}
async function renderSimpleTrips(kind='TRIP'){
  const isSocp=siteId==='SOCP';
  const title=siteId==='KOCP'?(kind==='OB'?'KOCP OB Entry':'KOCP Coal Entry'):'SOCP Trip Entry';
  const desc=isSocp?'Batch daily trip entry. Set the repeated shift/loader/unloading point once, then fill vehicles and quantities.':kind==='OB'?'Batch OB entry. Source, destination and material are captured; CuM/trip comes from the approved MCL rule.':'Batch Coal entry. Source, destination and material are captured; MT/trip comes from the approved MCL shift rule.';
  const rec=await api(`/api/sites/${siteId}/records/trips?operating_date=${state.ctx.operatingDate}&limit=60`).catch(()=>[]);
  const rows=rec.map(r=>`<tr><td>${esc(r.shift)}</td><td>${esc(r.vehicleId||r.vehicleRaw||'—')}</td><td>${esc(r.loadingEquipmentId||'—')}</td>${isSocp?'':`<td>${esc(r.sourceLocationId||'—')}</td>`}<td>${esc(r.destinationLocationId||'—')}</td>${isSocp?'':`<td>${esc(r.materialId||'—')}</td>`}<td>${esc(r.gpNo||'—')}</td><td>${fmt(r.quantityMt,3)}</td><td>${fmt(r.quantityCum,3)}</td><td>${esc(r.weightBasis||'—')}</td></tr>`);
  const defaults=isSocp
    ?`<div class="trip-default-grid">
        <div class="field"><span>Entry Date</span><input id="stDate" type="date" data-no-draft value="${state.ctx.operatingDate}"></div>
        <div class="field"><span>Default Shift</span><select id="stDefaultShift">${shiftOpts(simpleShift())}</select></div>
        ${defaultLookupBox('stDefaultLoader','Default Loader','LOADING,LOADER,EXCAVATOR')}
        ${defaultLookupBox('stDefaultDest','Default Unloading Point','LOCATION')}
        <div class="field"><span>Rows</span><select id="stRows" onchange="rebuildSimpleTripRows()"><option>5</option><option selected>10</option><option>20</option><option>30</option></select></div>
        <button class="btn outline apply-defaults-btn" onclick="applyTripDefaults()">Apply Defaults to Blank Rows</button>
      </div>`
    :`<div class="trip-default-grid kocp-defaults">
        <div class="field"><span>Entry Date</span><input id="stDate" type="date" data-no-draft value="${state.ctx.operatingDate}"></div>
        <div class="field"><span>Default Shift</span><select id="stDefaultShift">${shiftOpts(simpleShift())}</select></div>
        ${defaultLookupBox('stDefaultLoader','Default Loader / Excavator','LOADING,LOADER,EXCAVATOR')}
        ${defaultLookupBox('stDefaultSource','Default Source','LOCATION')}
        ${defaultLookupBox('stDefaultDest','Default Destination','LOCATION')}
        ${defaultLookupBox('stDefaultMaterial','Default Material','MATERIAL')}
        <div class="field"><span>Rows</span><select id="stRows" onchange="rebuildSimpleTripRows()"><option>5</option><option selected>10</option><option>20</option><option>30</option></select></div>
        <button class="btn outline apply-defaults-btn" onclick="applyTripDefaults()">Apply Defaults to Blank Rows</button>
      </div>`;
  const heads=isSocp
    ?'<th>#</th><th>Shift</th><th>Vehicle</th><th>Loader</th><th>Unloading Point</th><th>GP / Ref</th><th>Qty MT</th><th>Status</th>'
    :'<th>#</th><th>Shift</th><th>Vehicle</th><th>Loader / Excavator</th><th>Source</th><th>Destination</th><th>Material</th><th>GP / Ref</th><th>Quantity</th><th>Status</th>';
  const recentHeads=isSocp?['Shift','Vehicle','Loader','Destination','GP','MT','CuM','Basis']:['Shift','Vehicle','Loader/Excavator','Source','Destination','Material','GP','MT','CuM','Basis'];
  return simplePageHead(title,desc)+`<div id="simpleTripForm" class="simple-form batch-entry-form">
    ${defaults}
    <div class="entry-grid-note"><b>Fast entry:</b> Set repeated values above, click <b>Apply Defaults</b>, then enter only the changing vehicle/GP/quantity fields.</div>
    <div class="simple-table-wrap"><table class="simple-grid-table software-entry-grid trip-entry-grid"><thead><tr>${heads}</tr></thead><tbody id="simpleTripRows">${tripGridRows(kind,10)}</tbody></table></div>
    <div class="simple-actions"><button id="stSave" class="btn primary" onclick="saveSimpleTrips('${kind}')">Save Entered Rows</button><button class="btn outline" onclick="clearSimpleTripDraft()">Clear</button><span class="draft-state">Draft autosaves on this PC</span></div>
  </div>`+panel('Today’s Entries',recentTable(recentHeads,rows),`${rec.length} recent records`)
}
function rebuildSimpleTripRows(){
  const n=+$('stRows').value||10;
  $('simpleTripRows').innerHTML=tripGridRows(state.module==='OB'?'OB':'TRIP',n);
  bindLookups($('simpleTripForm'));
  restoreDraft('simpleTripForm',draftKey(state.module));
}
function copyLookupDefault(srcId,dstId){
  const src=$(srcId),dst=$(dstId),srcText=$(srcId+'Text'),dstText=$(dstId+'Text');
  if(!src||!dst||!src.value||dst.value)return;
  dst.value=src.value;
  if(srcText&&dstText){
    dstText.value=srcText.value;
    for(const k of ['vehicleNo','doorNo','group','type'])if(srcText.dataset[k])dstText.dataset[k]=srcText.dataset[k];
  }
}
function applyTripDefaults(){
  const sh=$('stDefaultShift')?.value;
  document.querySelectorAll('.simple-trip-row').forEach(row=>{
    const i=row.dataset.i,sel=row.querySelector('.stShift');if(sel&&sh)sel.value=sh;
    copyLookupDefault('stDefaultLoader',`stLoader${i}`);
    if(siteId==='SOCP') copyLookupDefault('stDefaultDest',`stDest${i}`);
    else{
      copyLookupDefault('stDefaultSource',`stSource${i}`);
      copyLookupDefault('stDefaultDest',`stDest${i}`);
      copyLookupDefault('stDefaultMaterial',`stMaterial${i}`);
    }
  });
  saveDraft('simpleTripForm',draftKey(state.module));
}
async function saveSimpleTrips(kind){
  const btn=$('stSave'),rows=[...document.querySelectorAll('.simple-trip-row')];
  let used=0,done=0;btn.disabled=true;
  try{
    for(const row of rows){
      const i=row.dataset.i,vehicle=$(`stVehicle${i}`).value,loader=$(`stLoader${i}`).value,gp=$(`stGp${i}`).value.trim();
      const destination=$(`stDest${i}`).value;
      const source=siteId==='KOCP'?$(`stSource${i}`).value:null;
      const material=siteId==='KOCP'?$(`stMaterial${i}`).value:null;
      const qty=siteId==='SOCP'?$(`stQty${i}`).value:'';
      if(!vehicle&&!loader&&!destination&&!source&&!material&&!gp&&!qty)continue;
      used++;const st=$(`stStatus${i}`);
      try{
        if(!vehicle)throw new Error('Select vehicle');
        if(!loader)throw new Error('Select loader/excavator');
        if(!destination)throw new Error(siteId==='SOCP'?'Select unloading point':'Select destination');
        if(siteId==='KOCP'&&!source)throw new Error('Select source');
        if(siteId==='KOCP'&&!material)throw new Error('Select material');
        if(siteId==='SOCP'&&!qty)throw new Error('Enter MT');
        st.textContent='Saving…';st.className='simple-status muted';
        const body={kind,operatingDate:$('stDate').value,shift:row.querySelector('.stShift').value,vehicleId:vehicle,loadingEquipmentId:loader,destinationLocationId:destination,gpNo:gp||null};
        if(siteId==='SOCP')body.quantityMt=qty;
        else{body.sourceLocationId=source;body.materialId=material}
        body.requestId=getReq(kind,body,i);
        const r=await api(`/api/site-ops/${siteId}/trips/simple`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        st.textContent=r.idempotent?'Already saved':'Saved ✓';st.className='simple-status good';clearReq(kind,i);done++;
      }catch(e){st.textContent=e.message;st.className='simple-status bad'}
    }
    if(!used)throw new Error('Enter at least one row');
    if(done===used){clearDraft('simpleTripForm',draftKey(kind));clearReq(kind);toast(`${done} row${done===1?'':'s'} saved`);setTimeout(()=>render(),500)}
    else toast(`${done}/${used} rows saved. Correct the red rows.`,done?'good':'bad');
  }catch(e){toast(e.message,'bad')}finally{btn.disabled=false}
}
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
  const cfg=SIMPLE[siteId]||{entry:[],setup:[],review:[],control:[]};
  const visible=new Set(['DASHBOARD',...(cfg.entry||[]),...(cfg.setup||[]),...(cfg.review||[]),...(cfg.control||[])]);
  if(!visible.has(state.module) || (state.module!=='DASHBOARD'&&!authorised(state.module))) state.module='DASHBOARD';
  setSimpleNav();
  const a=META[state.module]||['--',state.module,''];
  $('crumbTop').textContent=`NMTPL / ${siteId}`;
  $('crumbTitle').textContent=state.module==='DASHBOARD'?'Operations Dashboard':(label[state.module]||a[1]);
  let html=null;
  if(state.module==='DASHBOARD') html=await renderSimpleDashboard();
  else if(['TRIP','OB'].includes(state.module)) html=await renderSimpleTrips(state.module);
  else if(state.module==='WB') html=await renderSimpleWB();
  else if(state.module==='HSD') html=await renderSimpleHsd();
  else if(state.module==='HMR_KMR') html=await renderSimpleMeter();
  else{
    await baseRender();
    setSimpleNav();
    return;
  }
  if(html!==null&&typeof html==='string')$('workspace').innerHTML=html;
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
