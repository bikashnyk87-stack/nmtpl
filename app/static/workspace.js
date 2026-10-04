/* Shared compact workspace. Business workflows remain in webapp/legacy-shift. */
const pendingWrites = new Set(), readVersions = new Map();
let viewVersion = 0;
appRun = function(success, failure) {
  return new Proxy({}, {get: (_, method) => (...args) => {
    const read = method.startsWith('get'), version = (readVersions.get(method)||0)+1, view = viewVersion;
    if (!read && pendingWrites.has(method)) { toast('This action is already saving.'); return; }
    if(read) readVersions.set(method,version); else pendingWrites.add(method);
    return request('rpc',{method,args}).then(result=>{
      if(read && (readVersions.get(method)!==version || view!==viewVersion)) return;
      if(success) success(result);
    }).catch(error=>{
      if(view!==viewVersion) return;
      if(failure) failure(error); else toast(error.message,true);
    }).finally(()=>{if(!read) pendingWrites.delete(method);});
  }});
};
const renderOriginal = render;
render = function(screen){viewVersion++; document.body.classList.add('signed-in'); renderOriginal(screen); document.querySelectorAll('#nav button').forEach(b=>b.setAttribute('aria-current',b.id==='nav_'+screen?'page':'false'));};
const loginOriginal = showLogin;
showLogin = function(setup){viewVersion++;document.body.classList.remove('signed-in');loginOriginal(setup);};

function installDashboardV2Styles(){
  if(document.getElementById('dashboard_v2_styles'))return;
  const el=document.createElement('style');el.id='dashboard_v2_styles';el.textContent=`
  body.dashboard-v2 .page-heading{margin-bottom:7px;align-items:center}body.dashboard-v2 .page-heading .note{display:none}
  body.dashboard-v2 .page-heading h1{font-size:20px;margin-bottom:0}body.dashboard-v2 .page-heading .eyebrow{font-size:8px}
  body.dashboard-v2 .dashboard-toolbar{padding:7px 9px;margin-bottom:7px;gap:7px}body.dashboard-v2 .dashboard-context{margin:0 0 6px;display:flex;gap:6px;flex-wrap:wrap}
  body.dashboard-v2 .dashboard-context>*{font-size:9px;padding:2px 6px}body.dashboard-v2 .dashboard-kpis{grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:6px;margin-bottom:7px}
  body.dashboard-v2 .dashboard-kpis .command-kpi{min-height:68px;padding:8px 9px}body.dashboard-v2 .dashboard-kpis .command-kpi b{font-size:19px;margin:2px 0 0}
  body.dashboard-v2 .dashboard-kpis .command-kpi span{font-size:9px}body.dashboard-v2 .dashboard-kpis .command-kpi small{font-size:8px}
  body.dashboard-v2 .dash-grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:8px}body.dashboard-v2 .dash-span-4{grid-column:span 4}body.dashboard-v2 .dash-span-6{grid-column:span 6}body.dashboard-v2 .dash-span-8{grid-column:span 8}body.dashboard-v2 .dash-span-12{grid-column:1/-1}
  body.dashboard-v2 .dash-grid .panel{margin:0;padding:10px}body.dashboard-v2 .dash-grid h3{margin:0;font-size:12px}body.dashboard-v2 .dash-grid .sectionbar{margin-bottom:7px}
  .dash-chart{min-height:160px}.dash-bar-list{display:grid;gap:5px}.dash-bar-row{display:grid;grid-template-columns:minmax(90px,150px) 1fr 82px;gap:7px;align-items:center;font-size:10px}
  .dash-bar-track{height:9px;background:#edf2f4;border-radius:8px;overflow:hidden}.dash-bar-fill{height:100%;background:linear-gradient(90deg,#167a91,#08a084);border-radius:8px}.dash-bar-val{text-align:right;font-weight:650;color:#294c58}
  .dash-pie-wrap{display:grid;grid-template-columns:128px 1fr;gap:12px;align-items:center}.dash-pie{width:118px;height:118px;border-radius:50%;position:relative;margin:auto}.dash-pie:after{content:'';position:absolute;inset:29px;border-radius:50%;background:#fff;box-shadow:0 0 0 1px #eef2f3}.dash-legend{display:grid;gap:5px;font-size:10px}.dash-legend-row{display:grid;grid-template-columns:10px 1fr auto;gap:6px;align-items:center}.dash-dot{width:8px;height:8px;border-radius:2px}
  .dash-line{width:100%;height:150px}.dash-line text{font-size:8px;fill:#6b7d85}.dash-line .axis{stroke:#dbe4e8;stroke-width:1}.dash-line .series{fill:none;stroke:#167a91;stroke-width:2.5}.dash-line .point{fill:#fff;stroke:#167a91;stroke-width:2}
  .dash-mini-table .tablewrap{max-height:250px}.dash-mini-table table{font-size:10px}.dash-mini-table th{padding:6px 7px;font-size:9px}.dash-mini-table td{padding:5px 7px}
  .dash-status{display:grid;grid-template-columns:repeat(4,1fr);gap:5px}.dash-status>div{padding:7px;background:#f6f9fa;border:1px solid #e4ebee;border-radius:6px}.dash-status b{display:block;font-size:18px;color:#1d5664}.dash-status span{font-size:9px;color:#6b7d85}
  .dash-section-title{display:flex;justify-content:space-between;align-items:center;gap:8px}.dash-section-title .sub{font-size:9px;color:#70818a}
  @media(max-width:1100px){body.dashboard-v2 .dash-span-4,body.dashboard-v2 .dash-span-6,body.dashboard-v2 .dash-span-8{grid-column:span 6}}
  @media(max-width:760px){body.dashboard-v2 .dash-span-4,body.dashboard-v2 .dash-span-6,body.dashboard-v2 .dash-span-8{grid-column:1/-1}.dash-pie-wrap{grid-template-columns:1fr}.dash-bar-row{grid-template-columns:minmax(80px,110px) 1fr 70px}}
  `;document.head.appendChild(el);
}
function dashBarChart(rows,valueKey,labelKey,unit,secondaryKey){
  rows=(rows||[]).slice(0,10);if(!rows.length)return '<div class="emptyviz">No data in this period</div>';
  const max=Math.max(...rows.map(x=>Number(x[valueKey]||0)),1);
  return `<div class="dash-bar-list">${rows.map(x=>{const v=Number(x[valueKey]||0), sec=secondaryKey?` · ${num(x[secondaryKey])} trips`:'';return `<div class="dash-bar-row"><span title="${esc(x[labelKey])}">${esc(x[labelKey])}</span><div class="dash-bar-track"><div class="dash-bar-fill" style="width:${Math.max(1,v/max*100)}%"></div></div><span class="dash-bar-val">${num(v,1)}${unit||''}${sec}</span></div>`}).join('')}</div>`;
}
function dashPie(rows,valueKey,labelKey){
  rows=(rows||[]).filter(x=>Number(x[valueKey]||0)>0);if(!rows.length)return '<div class="emptyviz">No data in this period</div>';
  const top=rows.slice(0,6), rest=rows.slice(6).reduce((a,x)=>a+Number(x[valueKey]||0),0);if(rest>0)top.push({[labelKey]:'Other',[valueKey]:rest});
  const total=top.reduce((a,x)=>a+Number(x[valueKey]||0),0)||1, colors=['#167a91','#08a084','#5b8def','#e9a23b','#9b6bd3','#d25d67','#7d8c92'];let at=0;
  const stops=top.map((x,i)=>{const from=at,to=at+Number(x[valueKey]||0)/total*100;at=to;return `${colors[i%colors.length]} ${from}% ${to}%`}).join(',');
  return `<div class="dash-pie-wrap"><div class="dash-pie" style="background:conic-gradient(${stops})"></div><div class="dash-legend">${top.map((x,i)=>`<div class="dash-legend-row"><i class="dash-dot" style="background:${colors[i%colors.length]}"></i><span>${esc(x[labelKey])}</span><b>${num(Number(x[valueKey]||0)/total*100,1)}%</b></div>`).join('')}</div></div>`;
}
function dashLine(rows){
  rows=rows||[];if(!rows.length)return '<div class="emptyviz">No hourly WB data</div>';
  const W=620,H=150,P=24,max=Math.max(...rows.map(x=>Number(x.tonnes||0)),1),minHour=Math.min(...rows.map(x=>parseInt(x.hour,10))),maxHour=Math.max(...rows.map(x=>parseInt(x.hour,10))),span=Math.max(1,maxHour-minHour);
  const pts=rows.map(x=>{const h=parseInt(x.hour,10),v=Number(x.tonnes||0),px=P+(h-minHour)/span*(W-P*2),py=H-P-v/max*(H-P*2);return [px,py,x]}), path=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  return `<svg class="dash-line" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Hourly WB tonnes"><line class="axis" x1="${P}" y1="${H-P}" x2="${W-P}" y2="${H-P}"/><line class="axis" x1="${P}" y1="${P}" x2="${P}" y2="${H-P}"/><path class="series" d="${path}"/>${pts.map(p=>`<circle class="point" cx="${p[0]}" cy="${p[1]}" r="3"><title>${esc(p[2].hour)}: ${num(p[2].tonnes,1)} t / ${num(p[2].trips)} trips</title></circle>`).join('')}<text x="${P}" y="${H-5}">${esc(rows[0].hour)}</text><text x="${W-P-30}" y="${H-5}">${esc(rows[rows.length-1].hour)}</text><text x="${P+3}" y="${P+8}">${num(max,1)} t</text></svg>`;
}
function dashTable(headers,rows){return `<div class="dash-mini-table">${table(headers,rows)}</div>`;}

function dashTargets(){
  try{const x=JSON.parse(localStorage.getItem('nmtpl.dashboard.targets.v2')||'{}');return{day:Number(x.day||0),month:Number(x.month||0)}}catch(_){return{day:0,month:0}}
}
function dashSetTargets(){
  const t=dashTargets(), day=prompt('Daily production target (tonnes). Enter 0 to clear.',t.day||'' );if(day===null)return;
  const month=prompt('Monthly production target (tonnes). Enter 0 to clear.',t.month||'');if(month===null)return;
  const d=Math.max(0,Number(day)||0),m=Math.max(0,Number(month)||0);localStorage.setItem('nmtpl.dashboard.targets.v2',JSON.stringify({day:d,month:m}));loadDashboard();
}
function dashTone(v,good,warn){if(v==null||!isFinite(Number(v)))return'neutral';return Number(v)>=good?'good':Number(v)>=warn?'warning':'critical'}
function dashCard(label,value,sub,tone){return `<div class="v2-kpi ${tone||'neutral'}"><span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(sub||'')}</small></div>`}
function dashMini(label,value,sub,tone){return `<div class="mini-kpi ${tone||'neutral'}"><span>${esc(label)}</span><b>${esc(value)}</b>${sub?`<small>${esc(sub)}</small>`:''}</div>`}
function dashFmt(v,d,unit){if(v===null||v===undefined||v==='')return'—';return num(v,d)+(unit||'')}
function dashBars(rows,labelKey,valueKey,unit,limit){
  rows=(rows||[]).slice(0,limit||10);if(!rows.length)return'<div class="emptyviz">No data in this period</div>';
  const max=Math.max(...rows.map(x=>Number(x[valueKey]||0)),1);
  return `<div class="v2-bars">${rows.map(x=>`<div class="v2-bar"><span title="${esc(x[labelKey])}">${esc(x[labelKey])}</span><div><i style="width:${Math.max(2,Number(x[valueKey]||0)/max*100)}%"></i></div><b>${dashFmt(x[valueKey],1,unit||'')}</b></div>`).join('')}</div>`;
}
function dashDonut(rows,labelKey,valueKey,clickable){
  rows=(rows||[]).filter(x=>Number(x[valueKey]||0)>0);if(!rows.length)return'<div class="emptyviz">No data in this period</div>';
  const total=rows.reduce((s,x)=>s+Number(x[valueKey]||0),0), colors=['#087e70','#23685f','#167a91','#d99725','#8b5fbf','#b14c45','#4f7d95','#6a8c55'];let offset=0;
  const rings=rows.map((x,i)=>{const pct=Number(x[valueKey]||0)/total*100,off=-offset;offset+=pct;const attr=clickable?` data-material="${esc(x[labelKey])}" onclick="dashFilterMaterial(this.dataset.material)" class="click-slice"`:'';return `<circle${attr} cx="62" cy="62" r="44" pathLength="100" fill="none" stroke="${colors[i%colors.length]}" stroke-width="20" stroke-dasharray="${pct} ${100-pct}" stroke-dashoffset="${off}" transform="rotate(-90 62 62)"><title>${esc(x[labelKey])}: ${dashFmt(x[valueKey],1,' t')} · ${num(pct,1)}%</title></circle>`}).join('');
  const legend=rows.map((x,i)=>{const pct=Number(x[valueKey]||0)/total*100;return `<button class="donut-legend" ${clickable?`data-material="${esc(x[labelKey])}" onclick="dashFilterMaterial(this.dataset.material)"`:''}><i style="background:${colors[i%colors.length]}"></i><span>${esc(x[labelKey])}</span><b>${dashFmt(x[valueKey],1,' t')}</b><small>${num(pct,1)}%</small></button>`}).join('');
  return `<div class="donut-wrap"><svg viewBox="0 0 124 124" role="img" aria-label="Distribution chart">${rings}<text x="62" y="58" text-anchor="middle">${num(total,0)}</text><text x="62" y="75" text-anchor="middle" class="donut-unit">tonnes</text></svg><div class="donut-legends">${legend}</div></div>`;
}
function dashLine(rows,series){
  rows=rows||[];if(!rows.length)return'<div class="emptyviz">No data in this period</div>';
  const W=720,H=210,L=42,R=18,T=22,B=32,pw=W-L-R,ph=H-T-B,colors=['#087e70','#d99725','#167a91'],labelStep=Math.max(1,Math.ceil(rows.length/12));
  const xs=i=>L+(rows.length===1?pw/2:i*pw/(rows.length-1));
  const pieces=series.map((s,si)=>{const vals=rows.map(x=>Number(x[s.key]||0)),max=Math.max(...vals,1);const pts=vals.map((v,i)=>`${xs(i)},${T+ph-(v/max*ph)}`).join(' ');const dots=vals.map((v,i)=>{const x=xs(i),y=T+ph-(v/max*ph),show=i%labelStep===0||i===vals.length-1;return `<circle cx="${x}" cy="${y}" r="3" fill="${colors[si%colors.length]}"><title>${esc(rows[i].label||rows[i].hour||rows[i].date||'')}: ${num(v,s.d||0)}${esc(s.unit||'')}</title></circle>${show?`<text class="data-label" x="${x}" y="${Math.max(10,y-7)}" text-anchor="middle" fill="${colors[si%colors.length]}">${num(v,s.d||0)}${esc(s.unit||'')}</text>`:''}`}).join('');return `<polyline fill="none" stroke="${colors[si%colors.length]}" stroke-width="2.5" points="${pts}"/>${dots}`}).join('');
  const labels=rows.map((x,i)=>i%Math.max(1,Math.ceil(rows.length/8))===0?`<text x="${xs(i)}" y="${H-8}" text-anchor="middle">${esc(x.label||x.hour||x.date||'')}</text>`:'').join('');
  const legend=series.map((s,i)=>`<span><i style="background:${colors[i%colors.length]}"></i>${esc(s.label)}</span>`).join('');
  return `<div class="svg-chart"><div class="chart-legend">${legend}</div><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><line x1="${L}" y1="${T+ph}" x2="${W-R}" y2="${T+ph}" class="axis"/>${pieces}${labels}</svg></div>`;
}

function dashTargetChart(d,target){
  if(!target||d.fromDate!==d.toDate)return'<div class="emptyviz">Set a daily target; hourly target comparison is shown for a single day.</div>';
  const rows=(d.hourly||[]).map(x=>({...x}));if(!rows.length)return'<div class="emptyviz">No hourly WB production yet.</div>';
  let cum=0;const shiftFactor=d.shift!=='ALL'?1/3:1;const periodTarget=target*shiftFactor, step=periodTarget/Math.max(rows.length,1);
  const data=rows.map((x,i)=>{cum+=Number(x.tonnes||0);return{label:x.hour,actual:cum,target:step*(i+1)}});
  return dashLine(data,[{key:'actual',label:'Actual cumulative',unit:' t',d:0},{key:'target',label:'Paced target',unit:' t',d:0}]);
}
function dashMaterialTable(rows){
  rows=rows||[];if(!rows.length)return'<div class="emptyviz">No material production</div>';const max=Math.max(...rows.map(x=>Number(x.tonnes||0)),1);
  return `<div class="compact-table"><table><thead><tr><th>Material</th><th>Trips</th><th>Today/Period T</th><th>Month T</th><th>Avg Payload</th><th>%</th></tr></thead><tbody>${rows.map(x=>`<tr class="click-row" data-material="${esc(x.label)}" onclick="dashFilterMaterial(this.dataset.material)"><td><b>${esc(x.label)}</b><div class="cellbar"><i style="width:${Number(x.tonnes||0)/max*100}%"></i></div></td><td>${num(x.trips)}</td><td>${num(x.tonnes,1)}</td><td>${num(x.monthTonnes,1)}</td><td>${num(x.avgPayload,2)}</td><td>${num(x.pct,1)}%</td></tr>`).join('')}</tbody></table></div>`;
}
function dashLocationPanel(rows,title){
  rows=(rows||[]).slice(0,12);return `<div class="split-table-chart"><div class="compact-table">${table(['Location','Trips','Tonnes','Avg Payload'],rows.map(x=>[esc(x.label),num(x.trips),num(x.tonnes,1),num(x.avgPayload,2)]))}</div>${dashBars(rows,'label','tonnes',' t',12)}</div>`;
}
function dashStackedMachines(rows){
  if(!rows||!rows.length)return'<div class="emptyviz">No crusher-classified WB movement in this period.</div>';
  const machines=[...new Set(rows.map(x=>x.machine))], mats=[...new Set(rows.map(x=>x.material))], colors=['#087e70','#167a91','#d99725','#8b5fbf','#b14c45'];
  return `<div class="machine-stack">${machines.map(m=>{const rr=rows.filter(x=>x.machine===m),total=rr.reduce((s,x)=>s+Number(x.tonnes||0),0);return `<div><b>${esc(m)}</b><div class="stackbar">${rr.map((x,i)=>`<i style="width:${total?Number(x.tonnes)/total*100:0}%;background:${colors[mats.indexOf(x.material)%colors.length]}" title="${esc(x.material)} · ${num(x.trips)} trips · ${num(x.tonnes,1)} t"></i>`).join('')}</div><small>${num(total,1)} t</small></div>`}).join('')}</div>`;
}
function dashGroupedMachines(rows){
  if(!rows||!rows.length)return'<div class="emptyviz">No screen/MSP-classified WB movement in this period.</div>';const max=Math.max(...rows.map(x=>Number(x.tonnes||0)),1);
  return `<div class="group-bars">${rows.slice(0,18).map(x=>`<div><span>${esc(x.machine)}<small>${esc(x.material)}</small></span><i style="width:${Number(x.tonnes||0)/max*100}%"></i><b>${num(x.tonnes,1)} t</b></div>`).join('')}</div>`;
}
function dashHeatmap(d){
  const mats=(d.heatmapMaterials||[]).slice(0,6), rows=d.heatmap||[];if(!mats.length||!rows.length)return'<div class="emptyviz">Exact WB↔field matches are required for machine/material attribution.</div>';
  let max=1;rows.forEach(r=>mats.forEach(m=>max=Math.max(max,Number((r.values[m]||{}).tonnes||0))));
  return `<div class="heatmap-wrap"><table class="heatmap"><thead><tr><th>Machine</th>${mats.map(m=>`<th>${esc(m)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr><th>${esc(r.machine)}<small>${esc(r.type||'')}</small></th>${mats.map(m=>{const v=r.values[m]||{},a=Math.min(.85,.12+Number(v.tonnes||0)/max*.73);return `<td style="background:rgba(8,126,112,${a})" title="${esc(m)} · ${num(v.trips||0)} trips · ${num(v.tonnes||0,1)} t"><b>${num(v.trips||0)}</b><small>${num(v.tonnes||0,0)}t</small></td>`}).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function dashFlow(rows){return `<div class="flow-strip">${(rows||[]).map((x,i)=>`${i?'<div class="flow-arrow">→</div>':''}<div class="flow-node"><b>${esc(x.stage)}</b><span>${num(x.trips)} trips</span><strong>${num(x.tonnes,1)} t</strong></div>`).join('')}</div>`}
function dashFilterMaterial(material){S.dashMaterialFilter=material||'';loadDashboard();}
function dashClearMaterial(){S.dashMaterialFilter='';loadDashboard();}
function dashPerformer(rows){return rows&&rows.length?`<div class="performers">${rows.map(x=>`<div><span>${esc(x.category)}</span><b>${esc(x.name)}</b><small>${num(x.trips)} trips · ${num(x.tonnes,1)} t</small></div>`).join('')}</div>`:'<div class="emptyviz">No exact matched production attribution yet.</div>'}
function dashAlerts(rows){return `<div class="alert-list">${(rows||[]).map(x=>`<div class="alert-row ${esc(x.severity)}"><i></i><span>${esc(x.label)}</span><b>${num(x.value)}</b></div>`).join('')}</div>`}

function dashFillSelect(id,values,label,current){const el=document.getElementById(id);if(!el)return;const keep=String(current??el.value??'');const rows=(values||[]).map(x=>{if(x&&typeof x==='object'){const id=String(x.id??x.value??'');const text=String(x.label??x.name??x.id??x.value??'');return{id,label:text||id}}const v=String(x??'');return{id:v,label:v}}).filter(x=>x.id||x.label);el.innerHTML=`<option value="">${esc(label)}</option>${rows.map(x=>`<option value="${esc(x.id)}" ${keep===x.id?'selected':''}>${esc(x.label)}${x.label&&x.id&&x.label!==x.id?' · '+esc(x.id):''}</option>`).join('')}`;el.value=keep}
function dashRefreshFilterOptions(d){dashFillSelect('dash_source',d.availableSources,'All sources',d.sourceFilter||'');dashFillSelect('dash_destination',d.availableDestinations,'All destinations',d.destinationFilter||'');dashFillSelect('dash_vehicle',d.availableVehicles,'All vehicles',d.vehicleFilter||'')}
function dashCsvCell(v){v=String(v??'');return /[",\n]/.test(v)?`"${v.replaceAll('"','""')}"`:v}
function dashDownloadText(name,text,type){const b=new Blob([text],{type:type||'text/plain'}),u=URL.createObjectURL(b),a=document.createElement('a');a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000)}
function dashboardCsv(){const d=S.dashboard||{},k=d.kpis||{},rows=[['SECTION','LABEL','VALUE'],...Object.entries(k).map(([a,b])=>['KPI',a,b]),...(d.materials||[]).map(x=>['MATERIAL',x.label,x.tonnes]),...(d.routes||[]).map(x=>['ROUTE',x.source+' → '+x.destination,x.tonnes])];dashDownloadText(`TIOM_Dashboard_${d.fromDate||''}_${d.toDate||''}.csv`,rows.map(r=>r.map(dashCsvCell).join(',')).join('\n'),'text/csv')}
function dashboardJson(){const d=S.dashboard||{};dashDownloadText(`TIOM_Dashboard_${d.fromDate||''}_${d.toDate||''}.json`,JSON.stringify(d,null,2),'application/json')}
function dashboardPrint(){window.print()}
async function dashboardShare(){const d=S.dashboard||{},k=d.kpis||{},text=`TIOM Dashboard ${d.fromDate||''} to ${d.toDate||''}\nWB ${num(k.wbTonnes||0,1)} t · ${num(k.wbTrips||0)} trips · Avg Lead ${num(k.avgLeadKm||0,3)} km · Lead Work ${num(k.leadTonKm||0,1)} t-km · HSD ${num(k.hsdLitres||0,1)} L · Utilization ${num(k.equipmentUtilization||0,1)}%`;if(navigator.share){await navigator.share({title:'TIOM Production Dashboard',text});}else{await navigator.clipboard?.writeText(text);toast('Dashboard summary copied.')}}
renderDashboard = function(){
  S.dashMode='TODAY';S.dashMaterialFilter='';
  html('app',`<div class="page-heading dashboard-heading"><div><div class="eyebrow">MINE OPERATIONS CONTROL ROOM</div><h1>Production Dashboard</h1></div><div class="head-actions"><button class="btn secondary small" onclick="dashSetTargets()">Targets ⚙</button><button class="btn secondary small" onclick="dashboardCsv()">CSV</button><button class="btn secondary small" onclick="dashboardJson()">JSON</button><button class="btn secondary small" onclick="dashboardPrint()">Print / PDF</button><button class="btn secondary small" onclick="dashboardShare()">Share</button><button class="btn secondary small" onclick="loadDashboard()">Refresh</button></div></div>
    <div class="panel dashboard-toolbar sticky-dashboard"><div class="range-switch" role="group" aria-label="Reporting period">${[['TODAY','Today'],['CURRENT_SHIFT','Current shift'],['7D','7 days'],['MTD','MTD'],['CUSTOM','Custom']].map(([id,label])=>`<button class="period ${id==='TODAY'?'on':''}" onclick="dashMode(this,'${id}')">${label}</button>`).join('')}</div>
    <div id="custom_dates" hidden><label>From<input id="dash_from" type="date" value="${esc(S.boot.today)}"></label><label>To<input id="dash_to" type="date" value="${esc(S.boot.today)}"></label></div>
    <label>Shift<select id="dash_shift" onchange="loadDashboard()"><option value="ALL">All shifts</option>${opt(S.boot.masters.shifts,x=>x,x=>x)}</select></label><label>Source<select id="dash_source" onchange="loadDashboard()"><option value="">All sources</option></select></label><label>Destination<select id="dash_destination" onchange="loadDashboard()"><option value="">All destinations</option></select></label><label>Vehicle<select id="dash_vehicle" onchange="loadDashboard()"><option value="">All vehicles</option></select></label><button id="dash_apply" class="btn primary small" hidden onclick="loadDashboard()">Apply</button></div>
    <div id="dashboard_body" aria-live="polite"><div class="loading">Loading control room…</div></div>`);loadDashboard();
};

dashMode=function(btn,mode){S.dashMode=mode;document.querySelectorAll('.period').forEach(x=>x.classList.toggle('on',x===btn));document.getElementById('custom_dates').hidden=mode!=='CUSTOM';document.getElementById('dash_apply').hidden=mode!=='CUSTOM';document.getElementById('dash_shift').value=mode==='CURRENT_SHIFT'?S.boot.shift:'ALL';document.getElementById('dash_shift').disabled=mode==='CURRENT_SHIFT';if(mode!=='CUSTOM'){document.getElementById('dash_to').value=S.boot.today;loadDashboard();}};

loadDashboard=function(){
  appRun(d=>{
    S.dashboard=d;dashRefreshFilterOptions(d);const k=d.kpis||{},targets=dashTargets(),days=Math.max(1,Math.round((new Date(d.toDate)-new Date(d.fromDate))/86400000)+1),periodTarget=targets.day?targets.day*days:0;
    const achievement=periodTarget?Number(k.wbTonnes||0)/periodTarget*100:null,remaining=periodTarget?Math.max(0,periodTarget-Number(k.wbTonnes||0)):null,remainingTrips=remaining!=null&&Number(k.avgPayload)>0?Math.ceil(remaining/Number(k.avgPayload)):null;
    const topCards=[
      ['WB Tonnes',dashFmt(k.wbTonnes,1,' t'),'Confirmed WB','good'],['WB Trips',dashFmt(k.wbTrips,0),'Confirmed WB','good'],['Avg Payload',dashFmt(k.avgPayload,2,' t'),'Ton / trip','neutral'],['Avg Lead',dashFmt(k.avgLeadKm,3,' km'),'Quantity-weighted lead','good'],['Lead Work',dashFmt(k.leadTonKm,1,' t-km'),'Operational haulage work','good'],['Lead Trips',dashFmt(k.leadResolvedTrips,0),'Lead master matched','neutral'],['Lead Missing',dashFmt(k.leadMissingTrips,0),'Needs route / RL / master',Number(k.leadMissingTrips)>0?'warning':'good'],['Field Trips',dashFmt(k.fieldTrips,0),'Application','neutral'],['Match Rate',dashFmt(k.matchRate,1,'%'),'WB reconciliation',dashTone(k.matchRate,90,75)],['Materials',dashFmt(k.materials,0),'WB materials','neutral'],['Sources',dashFmt(k.sources,0),'Loading points','neutral'],['Destinations',dashFmt(k.destinations,0),'Receiving points','neutral'],
      ['Working Equipment',dashFmt(k.workingEquipment,0),'Equipment-shifts','neutral'],['People Present',dashFmt(k.presentPeople,0),'Person-shifts','neutral'],['HSD Issued',dashFmt(k.hsdLitres,1,' L'),'Selected period','neutral'],['HSD / Tonne',dashFmt(k.hsdPerTonne,2,' L/t'),'Issued / WB tonnes','neutral'],
      ["Today's Target",targets.day?num(targets.day,0)+' t':'Not set','Targets ⚙','neutral'],['Achievement',achievement==null?'—':num(achievement,1)+'%',periodTarget?num(periodTarget,0)+' t period target':'Set target',achievement==null?'neutral':dashTone(achievement,100,80)],['Remaining Tonnes',remaining==null?'—':num(remaining,0)+' t','Against period target',remaining==null?'neutral':remaining===0?'good':'warning'],['Remaining Trips',remainingTrips==null?'—':num(remainingTrips),'At current avg payload',remainingTrips==null?'neutral':remainingTrips===0?'good':'warning'],
      ['Ore Tonnes',dashFmt(k.oreTonnes,1,' t'),'Non-waste/non-reject','good'],['Waste Tonnes',dashFmt(k.wasteTonnes,1,' t'),'OB / waste','neutral'],['ROM',dashFmt(k.romTonnes,1,' t'),'WB classified','neutral'],['Fines',dashFmt(k.finesTonnes,1,' t'),'WB classified','neutral'],['CLO',dashFmt(k.cloTonnes,1,' t'),'WB classified','neutral'],['Reject',dashFmt(k.rejectTonnes,1,' t'),'WB classified',Number(k.rejectTonnes)>0?'warning':'neutral'],['Crusher Feed',dashFmt(k.crusherFeed,1,' t'),'Destination classified','neutral'],['Screen Feed',dashFmt(k.screenFeed,1,' t'),'Screen/MSP destination','neutral']
    ];
    const opsCards=[
      ['Avg Cycle',dashFmt(k.avgCycleTime,1,' min'),'Start → unload'],['Avg Loading',dashFmt(k.avgLoadingTime,1,' min'),'Start → loaded'],['Avg Unloading','—','Not captured'],['Active Crushers',dashFmt(k.activeCrushers,0),'Master + attendance'],['Active Screens',dashFmt(k.activeScreens,0),'Master + attendance'],['Running Loaders',dashFmt(k.runningLoaders,0),'Activity proxy'],['Running Excavators',dashFmt(k.runningExcavators,0),'Activity proxy'],['Running Tippers',dashFmt(k.runningTippers,0),'Activity proxy'],['Idle Equipment',dashFmt(k.idleEquipment,0),'No recorded production'],['Equipment Utilization',dashFmt(k.equipmentUtilization,1,'%'),'Activity proxy'],['Fuel / Trip',dashFmt(k.fuelPerTrip,2,' L'),'Issued HSD'],['Avg Trips / Vehicle',dashFmt(k.avgTripsVehicle,1),'Selected period'],['Avg Trips / Loader',dashFmt(k.avgTripsLoader,1),'Exact matches'],['Avg Trips / Excavator',dashFmt(k.avgTripsExcavator,1),'Exact matches'],['Avg Tonnes / Loader',dashFmt(k.avgTonnesLoader,1,' t'),'Exact matches'],['Avg Tonnes / Excavator',dashFmt(k.avgTonnesExcavator,1,' t'),'Exact matches'],['Total Routes',dashFmt(k.totalRoutes,0),'WB source → destination'],['Average Queue Time','—','Not captured']
    ];
    const materialFilter=d.materialFilter?`<button class="filter-chip" onclick="dashClearMaterial()">Material: ${esc(d.materialFilter)} ×</button>`:'';const extraFilters=[d.sourceFilter&&`Source: ${esc(d.sourceFilter)}`,d.destinationFilter&&`Destination: ${esc(d.destinationFilter)}`,d.vehicleFilter&&`Vehicle: ${esc(d.vehicleFilter)}`].filter(Boolean).map(x=>`<span class="filter-chip">${x}</span>`).join('');
    const hourly=(d.hourly||[]).map(x=>({label:x.hour,tonnes:x.tonnes,trips:x.trips}));
    const monthTarget=targets.month,monthAchievement=monthTarget?Number(d.monthly.actual||0)/monthTarget*100:null;
    const mgmt=[['Production',achievement==null?'—':num(achievement,0)+'%','Period target'],['Fleet Utilization',dashFmt(k.equipmentUtilization,1,'%'),'Activity proxy'],['Crusher Utilization','—','Runtime not captured'],['Fuel Efficiency',dashFmt(k.hsdPerTonne,2,' L/t'),'Issued / WB tonnes']];
    const crusherTable=table(['Crusher','Material','Trips','Tonnes','Avg Feed','Utilization'],(d.crusher||[]).map(x=>[esc(x.machine),esc(x.material),num(x.trips),num(x.tonnes,1),num(x.avgFeed,2),x.utilization==null?'—':num(x.utilization,1)+'%']));
    const screenTable=table(['Screen','Material','Trips','Tonnes','Recovery'],(d.screens||[]).map(x=>[esc(x.machine),esc(x.material),num(x.trips),num(x.tonnes,1),x.recovery==null?'—':num(x.recovery,1)+'%']));
    const loaderTable=table(['Loader','Trips','Tonnes','Avg Loading','Idle'],(d.loaders||[]).map(x=>[esc(x.machine),num(x.trips),num(x.tonnes,1),dashFmt(x.avgLoadingMin,1,' min'),'—']));
    const excTable=table(['Excavator','Trips','Tonnes','Avg Bucket','Loading'],(d.excavators||[]).map(x=>[esc(x.machine),num(x.trips),num(x.tonnes,1),'—',dashFmt(x.avgLoadingMin,1,' min')]));
    const vehicleTable=table(['Vehicle','Trips','Tonnes','Fuel','Avg Payload','Cycle','Status'],(d.vehicles||[]).map(x=>[esc(x.vehicle),num(x.trips),num(x.tonnes,1),num(x.fuel,1)+' L',num(x.avgPayload,2),dashFmt(x.cycleTime,1,' min'),`<span class="status-pill ${String(x.status).toLowerCase()}">${esc(x.status)}</span>`]));
    const routeTable=table(['Source','Destination','Trips','Tonnes','Avg Payload','Avg Time'],(d.routes||[]).slice(0,15).map(x=>[esc(x.source),esc(x.destination),num(x.trips),num(x.tonnes,1),num(x.avgPayload,2),dashFmt(x.avgTime,1,' min')]));
    const leadTable=table(['Source','Destination','Route','Trips','Avg Lead KM','Operational MT','Ton-KM'],(d.leadRoutes||[]).slice(0,30).map(x=>[esc(x.source),esc(x.destination),esc(String(x.routeMode||'').replaceAll('_',' ')),num(x.trips),num(x.avgLeadKm,3),num(x.tonnes,2),num(x.tonKm,1)]));
    const fuelTable=table(['Equipment','Type','Litres','Matched T','L/T'],(d.fuelByEquipment||[]).slice(0,15).map(x=>[esc(x.machine),esc(x.type),num(x.litres,1),num(x.tonnes,1),x.litresPerTonne==null?'—':num(x.litresPerTonne,2)]));
    const shiftTable=table(['Shift','Trips','Tonnes','Fuel','Avg Payload'],(d.shiftComparison||[]).map(x=>[esc(x.shift),num(x.trips),num(x.tonnes,1),num(x.fuel,1)+' L',num(x.avgPayload,2)]));
    const monthlyCards=[['Month Target',monthTarget?num(monthTarget,0)+' t':'Not set'],['Month Actual',num(d.monthly.actual,1)+' t'],['Achievement',monthAchievement==null?'—':num(monthAchievement,1)+'%'],['Best Day',d.monthly.bestDay?d.monthly.bestDay+' · '+num(d.monthly.bestTonnes,0)+' t':'—'],['Worst Day',d.monthly.worstDay?d.monthly.worstDay+' · '+num(d.monthly.worstTonnes,0)+' t':'—'],['Avg Daily Production',num(d.monthly.avgDaily,1)+' t']];
    html('dashboard_body',`<div class="dashboard-context compact"><b>${esc(d.fromDate)}${d.fromDate!==d.toDate?' → '+esc(d.toDate):''}</b><span>${d.shift==='ALL'?'All permitted shifts':'Shift '+esc(d.shift)}</span>${materialFilter}${extraFilters}<span>Updated ${esc(new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit'}))}</span></div>
      <div class="v2-kpi-grid">${topCards.map(x=>dashCard(...x)).join('')}</div>
      <div class="ops-kpi-strip">${opsCards.map(x=>dashMini(...x)).join('')}</div>
      <div class="dashboard-grid two"><section class="panel v2-panel"><div class="v2-title"><h3>Material Production</h3><span>Click a row to filter</span></div>${dashMaterialTable(d.materials)}</section><section class="panel v2-panel"><div class="v2-title"><h3>Material Distribution</h3><span>Trips · tonnes · %</span></div>${dashDonut(d.materials,'label','tonnes',true)}</section></div>
      <div class="dashboard-grid two"><section class="panel v2-panel"><div class="v2-title"><h3>Loading Location</h3><span>Source WB movement</span></div>${dashLocationPanel(d.sources,'Loading')}</section><section class="panel v2-panel"><div class="v2-title"><h3>Destination</h3><span>Receiving point</span></div>${dashLocationPanel(d.destinations,'Destination')}</section></div>
      <div class="dashboard-grid two"><section class="panel v2-panel"><div class="v2-title"><h3>Crusher Wise Production</h3><span>WB CRUSH-classified flow</span></div>${dashStackedMachines(d.crusher)}<details><summary>Crusher table</summary>${crusherTable}</details></section><section class="panel v2-panel"><div class="v2-title"><h3>Screening Machine Dashboard</h3><span>WB SCREEN/MSP-classified flow</span></div>${dashGroupedMachines(d.screens)}<details><summary>Screen table</summary>${screenTable}</details></section></div>
      <div class="dashboard-grid two"><section class="panel v2-panel"><div class="v2-title"><h3>Hourly Trend</h3><span>Hourly tonnes + trips</span></div>${dashLine(hourly,[{key:'tonnes',label:'Tonnes',unit:' t',d:0},{key:'trips',label:'Trips',unit:'',d:0}])}</section><section class="panel v2-panel"><div class="v2-title"><h3>Production vs Target</h3><span>Hourly cumulative pace</span></div>${dashTargetChart(d,targets.day)}</section></div>
      <div class="dashboard-grid two"><section class="panel v2-panel"><div class="v2-title"><h3>Loader Productivity</h3><span>Exact WB matches</span></div>${loaderTable}<h3 class="subhead">Excavators</h3>${excTable}</section><section class="panel v2-panel"><div class="v2-title"><h3>Vehicle Productivity</h3><span>WB production + field cycle + HSD</span></div>${vehicleTable}</section></div>
      <div class="dashboard-grid two"><section class="panel v2-panel"><div class="v2-title"><h3>Machine vs Material Matrix</h3><span>Trips / tonnes</span></div>${dashHeatmap(d)}</section><section class="panel v2-panel"><div class="v2-title"><h3>Route Analysis</h3><span>Top routes by WB tonnes</span></div>${dashBars((d.routes||[]).map(x=>({label:x.source+' → '+x.destination,tonnes:x.tonnes})),'label','tonnes',' t',10)}<details><summary>Route table</summary>${routeTable}</details></section></div>
      <section class="panel v2-panel"><div class="v2-title"><h3>Lead Distance Control</h3><span>Approved lead master · submitted MIS rows · unresolved routes excluded from Ton-KM</span></div><div class="mini-summary">${dashMini('Avg Lead',dashFmt(k.avgLeadKm,3,' km'),'Qty-weighted')}${dashMini('Lead Work',dashFmt(k.leadTonKm,1,' t-km'),'Operational Ton-KM')}${dashMini('With WB',dashFmt(k.leadWithWbTrips,0),'Lead trips')}${dashMini('Without WB',dashFmt(k.leadWithoutWbTrips,0),'Lead trips')}${dashMini('Lead Missing',dashFmt(k.leadMissingTrips,0),'Needs master mapping',Number(k.leadMissingTrips)>0?'warning':'good')}</div>${leadTable}</section>
      <section class="panel v2-panel"><div class="v2-title"><h3>Material Flow</h3><span>Recorded/derived movement stages</span></div>${dashFlow(d.materialFlow)}</section>
      <div class="dashboard-grid two"><section class="panel v2-panel"><div class="v2-title"><h3>Fuel Dashboard</h3><span>Fuel issued · efficiency</span></div><div class="mini-summary">${dashMini('Fuel Issued',num(k.hsdLitres,1)+' L')}${dashMini('Fuel Consumed','—','Not captured')}${dashMini('Fuel / Ton',num(k.hsdPerTonne,2)+' L/t')}${dashMini('Fuel / Trip',num(k.fuelPerTrip,2)+' L')}</div>${dashBars(d.fuelByEquipment,'machine','litres',' L',12)}<details><summary>Fuel detail</summary>${fuelTable}</details></section><section class="panel v2-panel"><div class="v2-title"><h3>Shift Comparison</h3><span>A / B / C</span></div>${shiftTable}${dashBars((d.shiftComparison||[]).map(x=>({label:'Shift '+x.shift,tonnes:x.tonnes})),'label','tonnes',' t',6)}</section></div>
      <div class="dashboard-grid two"><section class="panel v2-panel"><div class="v2-title"><h3>7-Day Trend</h3><span>Production + trips</span></div>${dashLine((d.sevenDay||[]).map(x=>({label:String(x.date).slice(5),tonnes:x.tonnes,trips:x.trips})),[{key:'tonnes',label:'Production',unit:' t',d:0},{key:'trips',label:'Trips',unit:'',d:0}])}<div class="fuel-trend">Fuel: ${(d.sevenDay||[]).map(x=>`${esc(String(x.date).slice(5))} ${num(x.fuel,0)}L`).join(' · ')}</div></section><section class="panel v2-panel"><div class="v2-title"><h3>Monthly Summary</h3><span>MTD through ${esc(d.toDate)}</span></div><div class="monthly-grid">${monthlyCards.map(x=>dashMini(x[0],x[1])).join('')}</div></section></div>
      <div class="dashboard-grid two"><section class="panel v2-panel"><div class="v2-title"><h3>Equipment Status</h3><span>Latest recorded condition</span></div>${dashDonut((d.equipmentStatus||[]).map(x=>({label:x.label,tonnes:x.value})),'label','tonnes',false)}</section><section class="panel v2-panel"><div class="v2-title"><h3>Alerts</h3><span>Green · warning · critical</span></div>${dashAlerts(d.exceptions)}</section></div>
      <div class="dashboard-grid three"><section class="panel v2-panel"><div class="v2-title"><h3>Top Performers</h3><span>Trips + tonnes</span></div>${dashPerformer(d.topPerformers)}</section><section class="panel v2-panel"><div class="v2-title"><h3>Bottom Performers</h3><span>Lowest recorded trip output</span></div>${dashPerformer(d.bottomPerformers)}</section><section class="panel v2-panel management"><div class="v2-title"><h3>Management Summary</h3><span>At a glance</span></div>${mgmt.map(x=>dashMini(x[0],x[1],x[2])).join('')}<div class="weather-placeholder"><b>Weather</b><span>Not configured — site weather source/coordinates required.</span></div></section></div>
      <details class="panel data-notes"><summary>Data coverage / calculation notes</summary><p>${(d.notes||[]).map(esc).join(' ')}</p><p><b>Not captured:</b> true unloading duration, queue time, bucket count, crusher runtime utilization, screen recovery, and weather.</p></details>`);
  },e=>html('dashboard_body','<div class="panel bad" role="alert">'+esc(e.message)+' <button class="btn secondary" onclick="loadDashboard()">Retry</button></div>')).getDashboard({mode:S.dashMode,fromDate:val('dash_from'),toDate:val('dash_to'),shift:val('dash_shift')||'ALL',materialFilter:S.dashMaterialFilter||'',sourceFilter:val('dash_source')||'',destinationFilter:val('dash_destination')||'',vehicleFilter:val('dash_vehicle')||''});
};
const masterConfig={
  PERSON:{key:'persons',label:'People',fields:['id','name','role','department','rotationTeam','active']},
  EQUIPMENT:{key:'equipment',label:'Equipment',fields:['id','doorNo','vehicleNo','type','group','makeModel','bucketCum','ratedPayloadT','ratedOutputTph','standingTareKg','ownership','active']},
  LOCATION:{key:'locations',label:'Locations',fields:['id','name','role','type','active']},
  LOCATION_ALIAS:{key:'locationAliases',label:'Location aliases',fields:['id','locationId','direction','active']},
  WBHEADER:{key:'wbHeaders',label:'WB Header Mapping',fields:['field','header','occurrence','priority','required','active']},
  PRODUCT:{key:'products',label:'Products',fields:['id','name','active']},
  ACTIVITY:{key:'activities',label:'Activities',fields:['id','vehicleRequired','active']},
  TANKER:{key:'tankers',label:'HSD tankers',fields:['id','vehicleNo','capacity','active']}
};
const fieldLabels={
  id:'Record ID / Alias',name:'Name',role:'Role',department:'Department',rotationTeam:'Rotation team',active:'Status',
  doorNo:'Door number',vehicleNo:'Vehicle / registration number',type:'Type',group:'Equipment group',makeModel:'Make / model',ownership:'Ownership',
  bucketCum:'Bucket capacity (cum)',ratedPayloadT:'Rated payload (t)',ratedOutputTph:'Rated output (t/hr)',standingTareKg:'Standing tare (kg)',
  vehicleRequired:'Vehicle required',capacity:'Capacity (litres)',locationId:'Canonical location',
  direction:'Alias use',field:'Standard WB field',header:'Excel header alias',occurrence:'Header occurrence',
  priority:'Priority',required:'Required header'
};
const categoryDefaults={
  'PERSON.role':['DRIVER','EXCAVATOR OPERATOR','LOADER OPERATOR','SUPERVISOR','HELPER'],
  'PERSON.department':['OPERATIONS','MAINTENANCE','ADMINISTRATION'],
  'EQUIPMENT.type':['Tipper','Dumper','Excavator','Loader','Crusher','Screen','Dozer','Grader','Drill','Tanker','Support'],
  'EQUIPMENT.group':['LOADING','TRANSPORT','PROCESSING','EARTHMOVING','DRILLING','SUPPORT','HSD_TANKER','OTHER'],
  'EQUIPMENT.ownership':['OWN','HIRED'],
  'LOCATION.role':['SOURCE','DESTINATION','BOTH','UNCLASSIFIED'],
  'LOCATION.type':['PIT','QUARRY','LOADING_POINT','ROM_PAD','CRUSHER','SCREEN','STACK','STOCKYARD','WASTE_DUMP','SIDING','WEIGHBRIDGE','WORKSHOP','OTHER']
};
const categoryLimits={'PERSON.role':80,'PERSON.department':80,'EQUIPMENT.type':60,'EQUIPMENT.group':30,'EQUIPMENT.ownership':30,'LOCATION.role':20,'LOCATION.type':60};
const wbCanonicalFields=[
  ['move','Movement number'],['date','Movement date'],['shift','Shift'],['vehicle','Vehicle'],
  ['matcode','Material code'],['matname','Material name'],
  ['source_code','Source code / ID'],['source_name','Source name'],
  ['dest_code','Destination code / ID'],['dest_name','Destination name'],
  ['tare','Tare weight'],['gross','Gross weight'],['net','Net weight'],['time','WB gross time']
];
let masterPage=0, masterEditing=null;

renderMasters=function(){
  masterPage=0;masterEditing=null;
  html('app',`<div class="page-heading"><div><div class="eyebrow">CONFIGURATION</div><h1>Masters</h1><p class="note">Maintain people, equipment, mine locations, WB aliases and header mappings in one place.</p></div><button class="btn secondary" onclick="loadMasters()">Refresh</button></div>
    <div class="panel master-toolbar">
      <label>Master<select id="master_type" onchange="masterPage=0;masterEditing=null;renderMasterTable()">${Object.entries(masterConfig).map(([k,c])=>`<option value="${k}">${c.label}</option>`).join('')}</select></label>
      <label class="search-label">Search<input id="master_search" type="search" placeholder="Search any field…" oninput="masterPage=0;renderMasterRows()"></label>
      <label>Status<select id="master_status" onchange="masterPage=0;renderMasterRows()"><option value="ALL">All records</option><option value="true">Active</option><option value="false">Inactive</option></select></label>
      ${S.boot.user.isManagement?'<button class="btn primary" onclick="editMaster(-1)">+ Add record</button>':''}
    </div>
    <div class="panel note"><b>ERP master rule:</b> one Equipment Master is used everywhere. One Location Master holds Source / Destination / Both role plus the physical type. New WB locations are auto-created as WB_AUTO and can be reviewed here. Location aliases are only alternate WB spellings/codes, not duplicate locations.</div>
    <div id="master_body"><div class="loading">Loading masters…</div></div>`);
  loadMasters();
};
loadMasters=function(){appRun(d=>{S.mastersDesk=d;renderMasterTable();}).getMastersDesk();};
renderMasterTable=function(){if(!S.mastersDesk||S.screen!=='MASTERS')return;html('master_body','<section id="master_editor" class="panel" hidden></section><div class="panel"><div id="master_records"></div><div id="master_pagination" class="pagination"></div></div>');renderMasterRows();};

function renderMasterRows(){
  if(!S.mastersDesk)return;
  const cfg=masterConfig[val('master_type')], query=val('master_search').toLowerCase(), status=val('master_status');
  const rows=(S.mastersDesk[cfg.key]||[]).map((row,index)=>({row,index}))
    .filter(({row})=>(status==='ALL'||String(row.active)===status)&&Object.values(row).some(v=>String(v??'').toLowerCase().includes(query)));
  const pages=Math.max(1,Math.ceil(rows.length/25));masterPage=Math.min(masterPage,pages-1);
  const headers=cfg.fields.map(f=>fieldLabels[f]);if(S.boot.user.isManagement)headers.push('Action');
  const bools=new Set(['active','vehicleRequired','required']);
  html('master_records',table(headers,rows.slice(masterPage*25,(masterPage+1)*25).map(({row,index})=>{
    const cells=cfg.fields.map(f=>{
      if(f==='active')return `<span class="tag ${row.active?'ok':''}">${row.active?'Active':'Inactive'}</span>`;
      if(bools.has(f))return row[f]?'Yes':'No';
      return esc(row[f]??'—');
    });
    if(S.boot.user.isManagement)cells.push(`<button class="btn secondary small" aria-label="Edit ${esc(row.id||row.field||'record')}" onclick="editMaster(${index})">Edit</button>`);
    return cells;
  })));
  html('master_pagination',`<span>${rows.length?masterPage*25+1:0}–${Math.min((masterPage+1)*25,rows.length)} of ${rows.length} records</span><div><button class="btn secondary small" ${masterPage===0?'disabled':''} onclick="masterPage--;renderMasterRows()">Previous</button><span> ${masterPage+1} / ${pages} </span><button class="btn secondary small" ${masterPage>=pages-1?'disabled':''} onclick="masterPage++;renderMasterRows()">Next</button></div>`);
}

function fieldOptions(t,f,current){
  if(f==='active')return [['true','Active'],['false','Inactive']];
  if(f==='vehicleRequired'||f==='required')return [['true','Yes'],['false','No']];
  if(f==='group')return ['LOADING','TRANSPORT','PROCESSING','EARTHMOVING','DRILLING','SUPPORT','HSD_TANKER','OTHER'].map(x=>[x,x.replaceAll('_',' ')]);
  if(f==='direction')return [['ANY','Any / both'],['SOURCE','Source only'],['DESTINATION','Destination only']];
  if(f==='locationId'){
    const rows=(S.mastersDesk.locations||[]).filter(x=>x.active);
    const opts=rows.map(x=>[x.id,x.id+' — '+x.name]);
    if(current&&!opts.some(x=>x[0]===current))opts.push([current,current+' (existing)']);
    return [['','Select location…'],...opts];
  }
  if(f==='field')return [['','Select standard field…'],...wbCanonicalFields];
  if(f==='rotationTeam'){
    const teams=(S.mastersDesk.rotationTeams||[]).map(x=>[x.id,x.name+' · '+x.id]);
    if(current&&!teams.some(x=>x[0]===current))teams.push([current,current+' (existing)']);
    return [['','Unassigned'],...teams];
  }
  const category=t+'.'+f;
  if(!(category in categoryDefaults))return null;
  const values=new Set([...(categoryDefaults[category]||[]),...(S.mastersDesk.options||[]).filter(x=>x.category===category).map(x=>x.value),...(S.mastersDesk[masterConfig[t].key]||[]).map(x=>x[f]).filter(Boolean)]);
  if(current)values.add(current);
  return [['','Select…'],...Array.from(values).sort().map(x=>[x,x])];
}

function editMaster(index){
  const t=val('master_type'),cfg=masterConfig[t];
  const row=index<0?{active:true,vehicleRequired:false,required:false,occurrence:1,priority:100,direction:'ANY'}:S.mastersDesk[cfg.key][index];
  masterEditing=index<0?null:row.id;
  const lengths={PERSON:40,EQUIPMENT:50,LOCATION:80,LOCATION_ALIAS:180,PRODUCT:50,ACTIVITY:60,TANKER:50,WBHEADER:120};
  const fields=cfg.fields.map(f=>{
    const choices=fieldOptions(t,f,row[f]),category=t+'.'+f,add=category in categoryDefaults||f==='rotationTeam';
    let control;
    if(choices){
      control=`<select id="mf_${f}" ${['role','group','type','locationId','field'].includes(f)?'required':''}>${choices.map(([v,l])=>`<option value="${esc(v)}" ${String(row[f]??'')===String(v)?'selected':''}>${esc(l)}</option>`).join('')}</select>`;
    }else if(['occurrence','priority','capacity','bucketCum','ratedPayloadT','ratedOutputTph','standingTareKg'].includes(f)){
      const decimal=['capacity','bucketCum','ratedPayloadT','ratedOutputTph','standingTareKg'].includes(f),min=decimal?'0':'1',step=decimal?'0.01':'1';
      control=`<input id="mf_${f}" value="${esc(row[f]??'')}" type="number" min="${min}" step="${step}" ${f==='capacity'?'required':''}>`;
    }else{
      const max=f==='header'?120:(f==='name'?(t==='LOCATION'?160:120):(f==='id'?(lengths[t]||80):80));
      const required=['id','name','header'].includes(f)&&!(t==='WBHEADER'&&f==='id');
      control=`<input id="mf_${f}" value="${esc(row[f]??'')}" ${f==='id'&&index>=0?'readonly':''} ${required?'required':''} maxlength="${max}">`;
    }
    return `<div class="master-field"><label for="mf_${f}">${fieldLabels[f]}</label><div class="field-control">${control}${add?`<button type="button" class="add-option" title="Add ${fieldLabels[f]} option" aria-label="Add ${fieldLabels[f]} option" onclick="openOption('${f}')">+</button>`:''}</div></div>`;
  }).join('');
  const label=index<0?'Add '+cfg.label:'Edit '+cfg.label+(row.id?' · '+row.id:'');
  const note=t==='WBHEADER'
    ?'Map every site Excel heading to one standard field. For duplicate headings, set occurrence 1 for the first column and 2 for the second.'
    :t==='LOCATION_ALIAS'
      ?'Use this when the WB code/name is different from the canonical Location ID used by field entry.'
      :(index<0?'Use a unique ID. Dropdown additions are saved for everyone.':'Record ID is fixed to preserve history. Set status to Inactive to retire a record.');
  const el=document.getElementById('master_editor');el.hidden=false;
  el.innerHTML=`<div class="sectionbar"><h3>${esc(label)}</h3><button type="button" class="btn secondary small" onclick="closeMasterEditor()">Cancel</button></div><form id="master_form"><div class="master-form">${fields}</div><div class="editor-footer"><span class="note">${esc(note)}</span><button class="btn primary" type="submit">${index<0?'Create record':'Save changes'}</button></div></form>`;
  document.getElementById('master_form').onsubmit=e=>{e.preventDefault();saveMasterUi();};
  el.scrollIntoView({block:'nearest'});
  const focusId=cfg.fields.includes('id')?'mf_id':cfg.fields.includes('field')?'mf_field':cfg.fields.includes('name')?'mf_name':null;
  if(focusId)document.getElementById(focusId)?.focus();
}
function closeMasterEditor(){document.getElementById('master_editor').hidden=true;masterEditing=null;}

saveMasterUi=function(){
  const t=val('master_type'),row={},bools=new Set(['active','vehicleRequired','required']);
  masterConfig[t].fields.forEach(f=>{row[f]=bools.has(f)?val('mf_'+f)==='true':val('mf_'+f).trim();});
  if(t==='WBHEADER'&&masterEditing!==null)row.id=masterEditing;
  appRun(r=>{toast(r.message);masterEditing=null;loadMasters();}).saveMasterRecord({table:t,row,intent:masterEditing===null?'create':'update'});
};

function openOption(field){
  const dlg=document.getElementById('option_dialog'),t=val('master_type'),team=field==='rotationTeam';
  dlg.innerHTML=`<form id="option_form"><h2 id="option_heading">Add ${fieldLabels[field]}</h2>${team?`<label>Team ID<input id="option_id" required maxlength="30"></label><label>Team name<input id="option_value" required maxlength="80"></label><label>Anchor Monday<input id="option_monday" type="date" required></label><label>Shift on that Monday<select id="option_shift"><option>A</option><option>B</option><option>C</option></select></label><p class="note">Weekly rotation follows A → C → B.</p>`:`<label>New option<input id="option_value" required maxlength="${categoryLimits[t+'.'+field]}" autocomplete="off"></label>`}<div id="option_error" role="alert"></div><div class="btnrow"><button type="button" class="btn secondary" onclick="document.getElementById('option_dialog').close()">Cancel</button><button class="btn primary">Save option</button></div></form>`;
  document.getElementById('option_form').onsubmit=e=>{
    e.preventDefault();
    const body=team?{id:val('option_id'),name:val('option_value'),monday:val('option_monday'),shift:val('option_shift')}:{category:t+'.'+field,value:val('option_value')};
    appRun(r=>{if(team)S.mastersDesk.rotationTeams.push({id:r.value,name:body.name});else S.mastersDesk.options.push({category:body.category,value:r.value});const select=document.getElementById('mf_'+field);select.add(new Option(r.value,r.value));select.value=r.value;dlg.close();toast(r.message);},e=>text('option_error',e.message))[team?'saveRotationTeam':'saveMasterOption'](body);
  };
  dlg.showModal();document.getElementById(team?'option_id':'option_value').focus();
}
