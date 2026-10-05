/* Volvo dashboard is intentionally isolated from TIOM operational writes. */
var VOLVO={data:null,map:null,route:null,routeSession:null,routeTripId:null,selectedVin:null,popupVin:null,timer:null,live:true,lastRouteLoad:0,drag:null,labels:false,zoneEditor:false,mapStyle:'street',showFleetMarkers:true};

async function volvoRequest(path,body){
  const opts={};
  if(body!==undefined){opts.method='POST';opts.headers={'Content-Type':'application/json'};opts.body=JSON.stringify(body);}
  return NMTPLNet.json('/api/volvo/'+path,opts);
}
function volvoDate(value){return value?new Date(value).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',hour12:true})+' IST':'—';}
function volvoNum(value,digits){if(value===null||value===undefined||Number.isNaN(Number(value)))return '—';return Number(value).toLocaleString('en-IN',{maximumFractionDigits:digits==null?1:digits});}
function volvoDay(iso,delta){const d=new Date(String(iso)+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+delta);return d.toISOString().slice(0,10);}
function volvoTruckArt(){return '<div class="volvo-truck" aria-hidden="true"><svg viewBox="0 0 360 170"><path fill="#dce9f3" d="M29 98h178V48h87l38 46v35h-15a35 35 0 0 0-69 0H131a35 35 0 0 0-69 0H29z"/><path fill="#7ab6df" d="M218 58h68l27 34h-95z"/><path fill="#0a3354" d="M25 40h170v51H25z"/><path fill="#1d6ca4" d="M41 54h138v23H41z"/><circle fill="#071b2b" cx="96" cy="132" r="27"/><circle fill="#cbd8e0" cx="96" cy="132" r="11"/><circle fill="#071b2b" cx="282" cy="132" r="27"/><circle fill="#cbd8e0" cx="282" cy="132" r="11"/><path fill="#fff" opacity=".75" d="M233 65h46l18 22h-64z"/></svg></div>';}
function volvoAge(seconds){if(seconds===null||seconds===undefined)return 'unknown';seconds=Number(seconds);if(seconds<60)return Math.round(seconds)+' sec';if(seconds<3600)return Math.round(seconds/60)+' min';return (seconds/3600).toFixed(1)+' h';}
function volvoTruckLabel(r){return r.machine_id?r.name+' · '+r.machine_id:r.name||r.vin;}
function volvoStateLabel(state){return state==='RUNNING'?'MOVING':state==='IDLE'?'ENGINE ON / IDLE':state==='STOPPED'?'STATIONARY':state||'—';}

function renderVolvo(){
  const today=(S.boot&&S.boot.today)||new Date().toISOString().slice(0,10),from=volvoDay(today,-6);
  if(VOLVO.timer){clearInterval(VOLVO.timer);VOLVO.timer=null;}
  VOLVO.route=null;VOLVO.routeSession=null;VOLVO.routeTripId=null;VOLVO.selectedVin=null;VOLVO.map=null;
  html('app','<div class="volvo-shell">'+
    '<div class="panel volvo-hero"><div><div class="eyebrow">VOLVO / GPS</div><h2>Fleet Live Status</h2><p>Operational status · moving trucks · GPS · fuel · route</p><div class="volvo-sync-pill"><span class="volvo-sync-dot"></span><span id="volvo_sync_text">Loading latest telemetry…</span></div></div></div>'+
    '<div class="panel volvo-filters">'+
      '<label>From date<input id="volvo_from" type="date" value="'+esc(from)+'"></label>'+
      '<label>To date<input id="volvo_to" type="date" value="'+esc(today)+'"></label>'+
      '<label>Truck / Machine<select id="volvo_machine"><option value="ALL">All Volvo trucks</option></select></label>'+
      '<label>Live movement<select id="volvo_state"><option value="ALL">All live states</option><option value="RUNNING">Moving now</option><option value="IDLE">Engine on / idle</option><option value="STOPPED">Stationary</option><option value="OFFLINE">Offline</option></select></label>'+
      '<label>Location<select id="volvo_location"><option value="ALL">All locations</option><option value="UNASSIGNED">Transit / outside zones</option></select></label>'+
      '<label>Shift<select id="volvo_shift"><option value="ALL">All shifts</option><option value="A">A · 06:00–14:00</option><option value="B">B · 14:00–22:00</option><option value="C">C · 22:00–06:00</option></select></label>'+
      '<label>Mapping<select id="volvo_mapping"><option value="ALL">Mapped + Unmapped</option><option value="MAPPED">Mapped only</option><option value="UNMAPPED">Unmapped only</option></select></label>'+
      '<div class="volvo-filter-actions"><button class="btn primary" onclick="loadVolvoDashboard()">Apply</button><button id="volvo_live_btn" class="btn secondary" onclick="toggleVolvoLive()">Live 30s: ON</button><button class="btn secondary" onclick="resetVolvoFilters()">Reset</button></div>'+
    '</div><div id="volvo_body"><div class="panel"><div class="loading">Loading Volvo dashboard…</div></div></div></div>');
  loadVolvoDashboard(true);
  VOLVO.timer=setInterval(function(){if(S.screen==='VOLVO'&&VOLVO.live)refreshVolvoLive();},30000);
}
function resetVolvoFilters(){const t=(S.boot&&S.boot.today)||new Date().toISOString().slice(0,10);document.getElementById('volvo_from').value=volvoDay(t,-6);document.getElementById('volvo_to').value=t;document.getElementById('volvo_machine').value='ALL';document.getElementById('volvo_state').value='ALL';document.getElementById('volvo_location').value='ALL';document.getElementById('volvo_shift').value='ALL';document.getElementById('volvo_mapping').value='ALL';VOLVO.route=null;VOLVO.routeSession=null;VOLVO.routeTripId=null;VOLVO.selectedVin=null;loadVolvoDashboard();}
function toggleVolvoLive(){VOLVO.live=!VOLVO.live;const b=document.getElementById('volvo_live_btn');if(b)b.textContent='Live 30s: '+(VOLVO.live?'ON':'OFF');}
function volvoQuery(){return new URLSearchParams({from_date:val('volvo_from'),to_date:val('volvo_to'),vehicle:val('volvo_machine')||'ALL',state:val('volvo_state')||'ALL',location:val('volvo_location')||'ALL',shift:val('volvo_shift')||'ALL',mapping:val('volvo_mapping')||'ALL'}).toString();}

async function loadVolvoDashboard(first,silent){
  try{
    const currentVehicle=val('volvo_machine')||'ALL',data=await volvoRequest('dashboard?'+volvoQuery());
    if(S.screen!=='VOLVO')return;VOLVO.data=data;
    const sync=document.getElementById('volvo_sync_text');if(sync)sync.textContent='Last collection: '+volvoDate(data.last_sync)+' · dashboard auto-refresh '+(VOLVO.live?'ON':'OFF');
    const machine=document.getElementById('volvo_machine'),vehicles=((data.filters&&data.filters.vehicles)||[]);
    if(first||machine.options.length!==vehicles.length+1){machine.innerHTML='<option value="ALL">All Volvo trucks</option>'+vehicles.map(x=>'<option value="'+esc(x.vin)+'">'+esc(x.label)+' · '+esc(x.vin.slice(-6))+'</option>').join('');machine.value=vehicles.some(x=>x.vin===currentVehicle)?currentVehicle:'ALL';}
    const location=document.getElementById('volvo_location'),currentLocation=(location&&location.value)||'ALL',locations=((data.filters&&data.filters.locations)||[]);
    if(location){location.innerHTML='<option value="ALL">All locations</option><option value="UNASSIGNED">Transit / outside zones</option>'+locations.map(x=>'<option value="'+esc(x.id)+'">'+esc(x.name)+(x.type?' · '+esc(x.type):'')+'</option>').join('');location.value=locations.some(x=>x.id===currentLocation)||currentLocation==='UNASSIGNED'?currentLocation:'ALL';}
    renderVolvoDashboardBody(data,!!silent);
    if(VOLVO.selectedVin&&VOLVO.live&&(Date.now()-VOLVO.lastRouteLoad>60000))loadVolvoRoute(VOLVO.selectedVin,true);
  }catch(e){if(S.screen==='VOLVO'&&!silent)html('volvo_body','<div class="panel bad">'+esc(e.message)+'</div>');}
}

function volvoApplyLiveFilters(rows){
  const vehicle=val('volvo_machine')||'ALL',state=val('volvo_state')||'ALL',location=val('volvo_location')||'ALL',mapping=val('volvo_mapping')||'ALL';
  return (rows||[]).filter(r=>{
    if(vehicle!=='ALL'&&![r.vin,r.machine_id,r.name].includes(vehicle))return false;
    if(state!=='ALL'&&r.state!==state)return false;
    if(location==='UNASSIGNED'&&r.location_id)return false;
    if(location!=='ALL'&&location!=='UNASSIGNED'&&r.location_id!==location)return false;
    if(mapping==='MAPPED'&&!r.machine_id)return false;
    if(mapping==='UNMAPPED'&&r.machine_id)return false;
    return true;
  });
}
function updateVolvoLiveKpis(fleet,operationalCount,currentShift){
  const counts={RUNNING:0,IDLE:0,STOPPED:0,OFFLINE:0};fleet.forEach(r=>{if(counts[r.state]!==undefined)counts[r.state]++;});
  const freshest=fleet.map(x=>Number(x.telemetry_age_seconds)).filter(Number.isFinite).sort((a,b)=>a-b)[0];
  const gps=fleet.filter(x=>volvoGpsOk(x.gps)).length;
  const values={
    volvo_kpi_fleet:fleet.length,
    volvo_kpi_operational:operationalCount==null?fleet.filter(x=>x.operational).length:operationalCount,
    volvo_kpi_moving:counts.RUNNING,
    volvo_kpi_stationary:counts.IDLE+counts.STOPPED,
    volvo_kpi_offline:counts.OFFLINE,
    volvo_kpi_gps:gps,
    volvo_kpi_fresh:volvoAge(freshest)
  };
  Object.keys(values).forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=String(values[id]);});
  const sh=document.getElementById('volvo_operational_shift');if(sh&&currentShift)sh.textContent='Shift '+currentShift;
  if(VOLVO.data){VOLVO.data.state_counts=counts;VOLVO.data.operational_count=values.volvo_kpi_operational;}
}

function refreshVolvoFleetTable(){
  const current=document.querySelector('.volvo-table tbody');if(!current||!VOLVO.data)return;
  const active=document.activeElement;
  if(active&&active.closest&&active.closest('.volvo-map-select'))return; // never destroy a mapping edit in progress
  const selections={};document.querySelectorAll('.volvo-map-select select').forEach(x=>{selections[x.id]=x.value;});
  const holder=document.createElement('div');holder.innerHTML=volvoFleetTable(VOLVO.data);
  const fresh=holder.querySelector('tbody');if(!fresh)return;current.innerHTML=fresh.innerHTML;
  Object.keys(selections).forEach(id=>{const x=document.getElementById(id);if(x)x.value=selections[id];});
}
async function refreshVolvoLive(){
  try{
    const live=await volvoRequest('fleet');if(S.screen!=='VOLVO'||!VOLVO.data)return;
    const fleet=volvoApplyLiveFilters(live.rows||[]);
    VOLVO.data.fleet=fleet;VOLVO.data.last_sync=live.last_sync;VOLVO.data.equipment=live.equipment||VOLVO.data.equipment;VOLVO.data.can_map=!!live.can_map;VOLVO.data.operational_count=live.operational_count;VOLVO.data.current_shift=live.current_shift;VOLVO.data.location_zones=live.location_zones||VOLVO.data.location_zones||[];
    const sync=document.getElementById('volvo_sync_text');if(sync)sync.textContent='Last collection: '+volvoDate(live.last_sync)+' · live fleet refresh '+(VOLVO.live?'ON':'OFF');
    updateVolvoLiveKpis(fleet,fleet.filter(x=>x.operational).length,live.current_shift);
    renderVolvoMap(fleet,true);
    refreshVolvoFleetTable();
    if(VOLVO.selectedVin&&(Date.now()-VOLVO.lastRouteLoad>60000))loadVolvoRoute(VOLVO.selectedVin,true);
  }catch(e){/* keep the last good dashboard visible if a live refresh fails */}
}

function renderVolvoDashboardBody(d,silent){
  const c=d.state_counts||{},t=d.totals||{},fleet=d.fleet||[],pv=d.period_vehicles||[],daily=d.daily||[];
  const freshest=fleet.map(x=>Number(x.telemetry_age_seconds)).filter(Number.isFinite).sort((a,b)=>a-b)[0];
  const operational=d.operational_count==null?fleet.filter(x=>x.operational).length:Number(d.operational_count);
  const stationary=(c.IDLE||0)+(c.STOPPED||0);
  const liveKpis=[
    ['Fleet',fleet.length,'trucks','volvo_kpi_fleet',''],
    ['Operational',operational,'Shift '+esc(d.current_shift||'—'),'volvo_kpi_operational','run'],
    ['Moving now',c.RUNNING||0,'speed > 1 km/h','volvo_kpi_moving','run'],
    ['Stationary now',stationary,'loading / queue / parked','volvo_kpi_stationary','idle'],
    ['Offline',c.OFFLINE||0,'telemetry > 120 min','volvo_kpi_offline','offline'],
    ['GPS online',fleet.filter(x=>volvoGpsOk(x.gps)).length,'latest position','volvo_kpi_gps','']
  ].map(x=>'<div class="volvo-kpi '+x[4]+'"><span>'+esc(x[0])+'</span><b id="'+x[3]+'">'+esc(String(x[1]))+'</b><small>'+esc(x[2])+'</small></div>').join('');
  const periodKpis=[
    ['Engine hours',volvoNum(t.engine_h,1)+' h'],
    ['Distance',volvoNum(t.distance_km,0)+' km'],
    ['Fuel used',volvoNum(t.fuel_l,0)+' L'],
    ['Avg fuel / hour',volvoNum(t.fuel_lph,2)+' L/h']
  ].map(x=>'<div class="volvo-period-kpi"><span>'+esc(x[0])+'</span><b>'+esc(x[1])+'</b></div>').join('');
  const status='<div class="volvo-simple-status">'+
    '<div><b>'+esc(operational)+'</b><span>Operational this shift</span></div>'+
    '<div><b>'+esc(c.RUNNING||0)+'</b><span>Moving now</span></div>'+
    '<div><b>'+esc(c.IDLE||0)+'</b><span>Engine on / idle</span></div>'+
    '<div><b>'+esc(c.STOPPED||0)+'</b><span>Stationary</span></div>'+
    '</div>';
  html('volvo_body',
    '<div class="volvo-section-title"><h3>Live fleet</h3><span id="volvo_operational_shift">Shift '+esc(d.current_shift||'—')+'</span></div>'+
    '<div class="volvo-kpis volvo-live-kpis">'+liveKpis+'</div>'+
    '<div class="volvo-section-title"><h3>Selected period</h3><span>'+esc(d.from_date)+' → '+esc(d.to_date)+' · Shift '+esc(d.shift||'ALL')+'</span></div>'+
    '<div class="volvo-period-kpis">'+periodKpis+'</div>'+
    '<div class="volvo-grid volvo-main-grid"><div id="volvo_map_panel" class="volvo-panel volvo-map-panel"><div class="volvo-panel-head"><h3>Live GPS Fleet Map</h3><div class="volvo-map-head-actions"><div class="volvo-basemap-toggle"><button id="volvo_map_street" class="btn small '+(VOLVO.mapStyle==='street'?'primary':'secondary')+'" onclick="setVolvoMapStyle(\'street\')">Map</button><button id="volvo_map_satellite" class="btn small '+(VOLVO.mapStyle==='satellite'?'primary':'secondary')+'" onclick="setVolvoMapStyle(\'satellite\')">Satellite</button></div><button class="btn secondary small" onclick="volvoFitFleet()">Fit fleet</button><button class="btn secondary small" onclick="volvoFitLocation()">Fit location</button><button id="volvo_fleet_marker_btn" class="btn secondary small" onclick="toggleVolvoFleetMarkers()">Hide trucks</button><button id="volvo_fullscreen_btn" class="btn secondary small" onclick="toggleVolvoMapFullscreen()">Full screen</button>'+(d.can_map?'<button class="btn secondary small" onclick="toggleVolvoZoneEditor()">Configure locations</button>':'')+'</div></div><div class="volvo-map-legend"><span><i class="moving"></i>Moving</span><span><i class="idle"></i>Engine on / idle</span><span><i class="stopped"></i>Stationary</span><span><em></em>Location zone</span></div>'+volvoLocationSummary(fleet,d.location_zones||[])+'<div id="volvo_map" class="volvo-map-wrap"></div><div id="volvo_zone_editor" class="volvo-zone-editor" hidden></div><div id="volvo_route_summary" class="volvo-route-summary">Select a truck marker or Track button to display its GPS trail.</div></div>'+
    '<div class="volvo-panel"><div class="volvo-panel-head"><h3>Live status</h3><span>Operational ≠ moving now</span></div><div class="volvo-panel-body">'+status+'<div class="volvo-footnote"><b>Operational</b> means the truck has shown movement, engine activity, fuel use or distance increase during the current shift. <b>Moving now</b> is only the latest speed reading. This prevents loading/unloading trucks from being shown as stopped operationally.</div><div class="volvo-fresh-line">Freshest telemetry: <b id="volvo_kpi_fresh">'+esc(volvoAge(freshest))+'</b></div></div></div></div>'+
    '<div class="volvo-section-title volvo-analytics-title"><h3>Fleet analytics</h3><span>Compact view · '+esc(d.from_date)+' → '+esc(d.to_date)+'</span></div>'+
    '<div class="volvo-mini-analytics-grid">'+
      volvoMiniChartPanel('Fuel','Top consumers',volvoMiniBars((pv||[]).slice().sort((a,b)=>Number(b.fuel_l||0)-Number(a.fuel_l||0)).slice(0,5),'fuel_l','L'))+
      volvoMiniChartPanel('Engine','Top hours',volvoMiniBars((pv||[]).slice().sort((a,b)=>Number(b.engine_h||0)-Number(a.engine_h||0)).slice(0,5),'engine_h','h'))+
      volvoMiniChartPanel('Distance','Top km',volvoMiniBars((pv||[]).slice().sort((a,b)=>Number(b.distance_km||0)-Number(a.distance_km||0)).slice(0,5),'distance_km','km'))+
      volvoMiniChartPanel('Daily trend','Fuel / distance',volvoMiniTrend(daily))+
    '</div>'+volvoFleetTable(d));
  renderVolvoMap(fleet,!!(silent&&VOLVO.map));
  if(VOLVO.route)setVolvoRouteSummary(VOLVO.route);
}

function volvoMiniChartPanel(title,sub,body){return '<div class="volvo-mini-chart"><div class="head"><div><b>'+esc(title)+'</b><span>'+esc(sub)+'</span></div></div><div class="body">'+body+'</div></div>';}
function volvoMiniBars(rows,key,suffix){
  rows=(rows||[]).filter(x=>x[key]!==null&&x[key]!==undefined);
  if(!rows.length)return '<div class="volvo-empty mini">No data</div>';
  const max=Math.max(...rows.map(x=>Number(x[key])||0),1);
  return '<div class="volvo-mini-bars">'+rows.map(x=>'<div class="row"><span title="'+esc(x.label)+'">'+esc(String(x.label||'').slice(0,10))+'</span><i><em style="width:'+Math.max(3,(Number(x[key])||0)/max*100).toFixed(1)+'%"></em></i><b>'+esc(volvoNum(x[key],0))+' '+esc(suffix)+'</b></div>').join('')+'</div>';
}
function volvoMiniTrend(rows){
  rows=(rows||[]).filter(x=>x.fuel_l!==null&&x.fuel_l!==undefined);
  if(rows.length<2)return '<div class="volvo-empty mini">No trend</div>';
  const W=260,H=105,L=8,R=8,T=8,B=18,n=Math.max(rows.length-1,1),maxFuel=Math.max(...rows.map(x=>Number(x.fuel_l)||0),1),maxKm=Math.max(...rows.map(x=>Number(x.distance_km)||0),1);
  const fuel=rows.map((r,i)=>[L+(W-L-R)*(i/n),T+(H-T-B)*(1-(Number(r.fuel_l)||0)/maxFuel)]).map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ');
  const km=rows.map((r,i)=>[L+(W-L-R)*(i/n),T+(H-T-B)*(1-(Number(r.distance_km)||0)/maxKm)]).map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ');
  return '<svg class="volvo-mini-trend" viewBox="0 0 '+W+' '+H+'"><polyline class="fuel" points="'+fuel+'"/><polyline class="distance" points="'+km+'"/></svg><div class="volvo-mini-legend"><span>Fuel</span><span>Distance</span></div>';
}
function volvoChartPanel(title,sub,body){return '<div class="volvo-panel"><div class="volvo-panel-head"><h3>'+esc(title)+'</h3><span>'+esc(sub)+'</span></div><div class="volvo-panel-body">'+body+'</div></div>';}
function volvoBars(rows,key,suffix){
  rows=(rows||[]).filter(x=>x[key]!==null&&x[key]!==undefined).slice().sort((a,b)=>Number(b[key])-Number(a[key])).slice(0,12);
  if(!rows.length)return '<div class="volvo-empty">Not enough history yet. The collector needs at least two saved readings inside the selected period/shift.</div>';
  const max=Math.max(...rows.map(x=>Number(x[key])||0),1);
  return '<div class="volvo-bars">'+rows.map(x=>'<div class="volvo-bar-row"><div class="volvo-bar-label" title="'+esc(x.label)+'">'+esc(x.label)+'</div><div class="volvo-bar-track"><div class="volvo-bar-fill" style="width:'+Math.max(1,(Number(x[key])||0)/max*100).toFixed(1)+'%"></div></div><div class="volvo-bar-value">'+esc(volvoNum(x[key],2)+suffix)+'</div></div>').join('')+'</div>';
}
function volvoStateDonut(counts,total){
  const parts=[
    {k:'RUNNING',label:'Moving',v:Number(counts.RUNNING)||0},
    {k:'IDLE',label:'Engine on / idle',v:Number(counts.IDLE)||0},
    {k:'STOPPED',label:'Stationary',v:Number(counts.STOPPED)||0},
    {k:'OFFLINE',label:'Offline',v:Number(counts.OFFLINE)||0}
  ];
  total=Math.max(Number(total)||parts.reduce((s,x)=>s+x.v,0),1);
  const r=54,cx=72,cy=72,C=2*Math.PI*r;
  let offset=0;
  const cls={RUNNING:'run',IDLE:'idle',STOPPED:'stopped',OFFLINE:'offline'};
  const arcs=parts.map(p=>{const len=C*(p.v/total),gap=Math.max(0,C-len);const s='<circle class="volvo-donut-seg '+cls[p.k]+'" cx="'+cx+'" cy="'+cy+'" r="'+r+'" stroke-dasharray="'+len+' '+gap+'" stroke-dashoffset="'+(-offset)+'"></circle>';offset+=len;return s;}).join('');
  const legend=parts.map(p=>'<div><span class="dot '+cls[p.k]+'"></span><b>'+esc(p.v)+'</b><em>'+esc(p.label)+'</em></div>').join('');
  return '<div class="volvo-donut-wrap"><svg viewBox="0 0 144 144" class="volvo-donut"><circle class="volvo-donut-bg" cx="'+cx+'" cy="'+cy+'" r="'+r+'"></circle>'+arcs+'<text x="'+cx+'" y="'+(cy-2)+'" text-anchor="middle" class="total">'+esc(total)+'</text><text x="'+cx+'" y="'+(cy+16)+'" text-anchor="middle" class="caption">trucks</text></svg><div class="volvo-donut-legend">'+legend+'</div></div>';
}
function volvoColumns(rows,key,suffix){
  rows=(rows||[]).filter(x=>x[key]!==null&&x[key]!==undefined).slice().sort((a,b)=>Number(b[key])-Number(a[key])).slice(0,12);
  if(!rows.length)return '<div class="volvo-empty">Not enough history for this metric.</div>';
  const W=680,H=230,L=34,R=14,T=20,B=58,max=Math.max(...rows.map(x=>Number(x[key])||0),1),slot=(W-L-R)/rows.length,bw=Math.max(12,slot*.58);
  const bars=rows.map((r,i)=>{const v=Number(r[key])||0,h=(H-T-B)*(v/max),x=L+i*slot+(slot-bw)/2,y=H-B-h,label=String(r.label||'').slice(0,8);return '<rect class="volvo-col" x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+h.toFixed(1)+'"><title>'+esc(r.label+' · '+volvoNum(v,1)+suffix)+'</title></rect><text x="'+(x+bw/2).toFixed(1)+'" y="'+(H-B+14)+'" text-anchor="middle">'+esc(label)+'</text><text class="value" x="'+(x+bw/2).toFixed(1)+'" y="'+Math.max(12,y-4).toFixed(1)+'" text-anchor="middle">'+esc(volvoNum(v,0))+'</text>';}).join('');
  return '<svg class="volvo-column-svg" viewBox="0 0 '+W+' '+H+'">'+bars+'</svg>';
}
function volvoFuelDistanceTrend(rows){
  rows=(rows||[]).filter(x=>x.fuel_l!==null&&x.fuel_l!==undefined);
  if(!rows.length)return '<div class="volvo-empty">No daily trend data for the selected period.</div>';
  const W=680,H=230,L=42,R=20,T=26,B=40,n=Math.max(rows.length-1,1),maxFuel=Math.max(...rows.map(x=>Number(x.fuel_l)||0),1),maxKm=Math.max(...rows.map(x=>Number(x.distance_km)||0),1);
  const fuel=rows.map((r,i)=>({x:L+(W-L-R)*(i/n),y:T+(H-T-B)*(1-(Number(r.fuel_l)||0)/maxFuel),d:r.date,v:Number(r.fuel_l)||0}));
  const km=rows.map((r,i)=>({x:L+(W-L-R)*(i/n),y:T+(H-T-B)*(1-(Number(r.distance_km)||0)/maxKm),d:r.date,v:Number(r.distance_km)||0}));
  const fPts=fuel.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' '),kPts=km.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' ');
  const labels=fuel.map(p=>'<text x="'+p.x+'" y="'+(H-12)+'" text-anchor="middle">'+esc(String(p.d).slice(5))+'</text>').join('');
  return '<div class="volvo-dual-legend"><span><i class="fuel"></i>Fuel L</span><span><i class="distance"></i>Distance km</span></div><svg class="volvo-dual-svg" viewBox="0 0 '+W+' '+H+'"><polyline class="fuel" points="'+fPts+'"/><polyline class="distance" points="'+kPts+'"/>'+labels+'</svg>';
}
function volvoAvailableHours(d){
  const a=new Date(String(d.from_date)+'T00:00:00Z'),b=new Date(String(d.to_date)+'T00:00:00Z');
  const days=Math.max(1,Math.round((b-a)/86400000)+1);
  return days*((d.shift&&d.shift!=='ALL')?8:24);
}
function volvoUtilizationBars(rows,d){
  const available=volvoAvailableHours(d);
  const data=(rows||[]).map(x=>Object.assign({},x,{utilization_pct:Math.min(100,available>0?(Number(x.engine_h)||0)/available*100:0)}));
  return volvoBars(data,'utilization_pct','%');
}
function volvoFuelSplit(rows){
  rows=(rows||[]).filter(x=>(Number(x.idle_fuel_l)||0)+(Number(x.moving_fuel_l)||0)>0).slice().sort((a,b)=>((Number(b.idle_fuel_l)||0)+(Number(b.moving_fuel_l)||0))-((Number(a.idle_fuel_l)||0)+(Number(a.moving_fuel_l)||0))).slice(0,12);
  if(!rows.length)return '<div class="volvo-empty">Idle/moving fuel counters are not available for this period.</div>';
  const max=Math.max(...rows.map(x=>(Number(x.idle_fuel_l)||0)+(Number(x.moving_fuel_l)||0)),1);
  return '<div class="volvo-stack-bars">'+rows.map(x=>{const idle=Number(x.idle_fuel_l)||0,moving=Number(x.moving_fuel_l)||0,total=idle+moving;return '<div class="volvo-stack-row"><div class="volvo-stack-label" title="'+esc(x.label)+'">'+esc(x.label)+'</div><div class="volvo-stack-track"><span class="moving" style="width:'+(moving/max*100).toFixed(1)+'%" title="Moving '+esc(volvoNum(moving,1))+' L"></span><span class="idle" style="width:'+(idle/max*100).toFixed(1)+'%" title="Idle '+esc(volvoNum(idle,1))+' L"></span></div><div class="volvo-stack-value">'+esc(volvoNum(total,1))+' L</div></div>';}).join('')+'<div class="volvo-stack-legend"><span><i class="moving"></i>Moving fuel</span><span><i class="idle"></i>Idle fuel</span></div></div>';
}
function volvoDotPlot(rows,key,suffix){
  rows=(rows||[]).filter(x=>x[key]!==null&&x[key]!==undefined).slice().sort((a,b)=>Number(b[key])-Number(a[key])).slice(0,12);
  if(!rows.length)return '<div class="volvo-empty">Not enough history for this metric.</div>';
  const max=Math.max(...rows.map(x=>Number(x[key])||0),1);
  return '<div class="volvo-dots">'+rows.map(x=>{const p=Math.max(1,(Number(x[key])||0)/max*100);return '<div class="volvo-dot-row"><div class="volvo-dot-label" title="'+esc(x.label)+'">'+esc(x.label)+'</div><div class="volvo-dot-track"><span style="width:'+p.toFixed(1)+'%"></span><i style="left:'+p.toFixed(1)+'%"></i></div><div class="volvo-dot-value">'+esc(volvoNum(x[key],1)+suffix)+'</div></div>';}).join('')+'</div>';
}
function volvoScatter(rows,xKey,yKey){
  rows=(rows||[]).filter(x=>Number.isFinite(Number(x[xKey]))&&Number.isFinite(Number(x[yKey]))).slice(0,50);
  if(!rows.length)return '<div class="volvo-empty">Not enough distance/fuel history yet.</div>';
  const W=680,H=240,L=48,R=20,T=24,B=42,maxX=Math.max(...rows.map(x=>Number(x[xKey])||0),1),maxY=Math.max(...rows.map(x=>Number(x[yKey])||0),1);
  const grid=[0,.25,.5,.75,1].map(q=>{const y=T+(H-T-B)*(1-q);const x=L+(W-L-R)*q;return '<line class="grid" x1="'+L+'" y1="'+y+'" x2="'+(W-R)+'" y2="'+y+'"/><line class="grid" x1="'+x+'" y1="'+T+'" x2="'+x+'" y2="'+(H-B)+'"/>';}).join('');
  const pts=rows.map(r=>{const x=L+(W-L-R)*(Number(r[xKey])||0)/maxX,y=T+(H-T-B)*(1-(Number(r[yKey])||0)/maxY);return '<circle class="scatter-dot" cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="5"><title>'+esc(r.label+' · '+volvoNum(r[xKey],1)+' km · '+volvoNum(r[yKey],1)+' L')+'</title></circle>';}).join('');
  return '<svg class="volvo-scatter-svg" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Distance versus fuel scatter plot">'+grid+pts+'<text x="'+((L+W-R)/2)+'" y="'+(H-8)+'" text-anchor="middle">Distance km →</text><text x="8" y="14">Fuel L ↑</text></svg>';
}
function volvoAreaLine(rows,key,suffix){
  rows=(rows||[]).filter(x=>x[key]!==null&&x[key]!==undefined);
  if(!rows.length)return '<div class="volvo-empty">No trend data for the selected period.</div>';
  const W=680,H=230,L=42,R=20,T=28,B=38,max=Math.max(...rows.map(x=>Number(x[key])||0),1),n=Math.max(rows.length-1,1);
  const pts=rows.map((x,i)=>({x:L+(W-L-R)*(i/n),y:T+(H-T-B)*(1-(Number(x[key])||0)/max),v:Number(x[key])||0,d:x.date}));
  const poly=pts.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' '),area=L+','+(H-B)+' '+poly+' '+(W-R)+','+(H-B);
  const labels=pts.map(p=>'<circle class="dot" cx="'+p.x+'" cy="'+p.y+'" r="4"><title>'+esc(p.d+' '+volvoNum(p.v,2)+suffix)+'</title></circle><text text-anchor="middle" x="'+p.x+'" y="'+(H-12)+'">'+esc(String(p.d).slice(5))+'</text>').join('');
  return '<svg class="volvo-line-svg volvo-area-svg" viewBox="0 0 '+W+' '+H+'"><polygon class="area" points="'+area+'"/><polyline class="line" points="'+poly+'"/>'+labels+'</svg>';
}
function volvoLine(rows,key,suffix){
  rows=(rows||[]).filter(x=>x[key]!==null&&x[key]!==undefined);
  if(!rows.length)return '<div class="volvo-empty">No trend data for the selected period.</div>';
  const W=680,H=230,L=42,R=20,T=28,B=38,max=Math.max(...rows.map(x=>Number(x[key])||0),1),n=Math.max(rows.length-1,1);
  const pts=rows.map((x,i)=>({x:L+(W-L-R)*(i/n),y:T+(H-T-B)*(1-(Number(x[key])||0)/max),v:Number(x[key])||0,d:x.date}));
  const grid=[0,.25,.5,.75,1].map(q=>{const y=T+(H-T-B)*(1-q);return '<line class="grid" x1="'+L+'" y1="'+y+'" x2="'+(W-R)+'" y2="'+y+'"/><text x="4" y="'+(y+3)+'">'+esc(volvoNum(max*q,0))+'</text>';}).join('');
  const poly=pts.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' '),labels=pts.map(p=>'<circle class="dot" cx="'+p.x+'" cy="'+p.y+'" r="4"><title>'+esc(p.d+' '+volvoNum(p.v,2)+suffix)+'</title></circle><text class="value" text-anchor="middle" x="'+p.x+'" y="'+Math.max(12,p.y-9)+'">'+esc(volvoNum(p.v,1))+'</text><text text-anchor="middle" x="'+p.x+'" y="'+(H-12)+'">'+esc(String(p.d).slice(5))+'</text>').join('');
  return '<svg class="volvo-line-svg" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Trend chart">'+grid+'<polyline class="line" points="'+poly+'"/>'+labels+'</svg>';
}

function volvoFleetTable(d){
  const rows=(d.fleet||[]).map(r=>{let link=esc(r.machine_id||'Unmapped');
    if(d.can_map){const opts=(d.equipment||[]).map(e=>'<option value="'+esc(e.id)+'" '+(r.machine_id===e.id?'selected':'')+'>'+esc(e.label)+' ('+esc(e.id)+')</option>').join('');link='<div class="volvo-map-select"><select id="volvo_link_'+esc(r.vin)+'"><option value="">Unmapped</option>'+opts+'</select><button class="btn secondary small" data-vin="'+esc(r.vin)+'" onclick="saveVolvoLink(this)">Save</button></div>';}
    const speed=Math.max(Number(r.wheel_speed_kmh)||0,Number(r.gps_speed_kmh)||0);
    return '<tr><td><div class="volvo-machine">'+esc(r.name||r.vin)+'</div><div class="volvo-vin">'+esc(r.vin)+(r.machine_id?' · TIOM '+esc(r.machine_id):'')+'</div></td>'+
      '<td><span class="volvo-operational '+(r.operational?'yes':'no')+'">'+(r.operational?'OPERATIONAL':'NO SHIFT ACTIVITY')+'</span></td>'+
      '<td><span class="volvo-badge '+esc(r.state)+'">'+esc(volvoStateLabel(r.state))+'</span></td>'+
      '<td>'+esc(r.location_name||'—')+'</td><td>'+esc(volvoNum(speed,1))+'</td><td>'+esc(volvoNum(r.fuel_level_pct,1))+'%</td><td>'+esc(volvoNum(r.engine_hours,1))+'</td>'+
      '<td>'+esc(volvoNum(r.distance_km,1))+'</td><td>'+esc(volvoAge(r.telemetry_age_seconds))+'</td>'+
      '<td><button class="btn secondary small" onclick="trackVolvo(\''+esc(r.vin)+'\')">Track</button></td><td>'+link+'</td></tr>';
  }).join('');
  return '<div class="volvo-panel" style="margin-top:14px"><div class="volvo-panel-head"><h3>Fleet detail</h3><div><button class="btn secondary small" onclick="volvoExportCsv()">Export full CSV</button></div></div>'+
    '<div class="volvo-table-wrap"><table class="volvo-table volvo-table-simple"><thead><tr><th>Truck</th><th>Shift status</th><th>Live state</th><th>Location</th><th>Speed km/h</th><th>Fuel</th><th>Engine h</th><th>Odometer km</th><th>Data age</th><th>Route</th><th>TIOM link</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+
    (rows?'':'<div class="volvo-empty">No vehicles match these filters.</div>')+'</div>';
}

async function saveVolvoLink(btn){btn.disabled=true;try{const vin=btn.dataset.vin,machine=document.getElementById('volvo_link_'+vin).value||null;await volvoRequest('mapping',{vin:vin,machine_id:machine});toast('Volvo vehicle mapping saved.');await loadVolvoDashboard();}catch(e){toast(e.message,true);}finally{btn.disabled=false;}}
function volvoExportCsv(){if(!VOLVO.data)return;const head=['VolvoName','MachineID','VIN','State','WheelSpeedKmh','GpsSpeedKmh','EngineRPM','FuelLevelPct','AdBluePct','EngineHours','DistanceKm','TotalFuelL','IdleFuelL','MovingFuelL','GrossWeightKg','AxleTotalKg','MovingHours','StationaryHours','Driver','ServiceDistanceKm','CoolantC','WarningCount','Latitude','Longitude','TelemetryAgeSeconds','ReportedAt'];const rows=(VOLVO.data.fleet||[]).map(r=>[r.name||'',r.machine_id||'',r.vin,r.state,r.wheel_speed_kmh??'',r.gps_speed_kmh??'',r.engine_speed_rpm??'',r.fuel_level_pct??'',r.adblue_pct??'',r.engine_hours??'',r.distance_km??'',r.fuel_used_l??'',r.idle_fuel_l??'',r.moving_fuel_l??'',r.gross_weight_kg??'',r.axle_total_kg??'',r.moving_h??'',r.stationary_h??'',r.driver_id||'',r.service_distance_km??'',r.coolant_temp_c??'',r.warning_count??'',r.gps&&r.gps.latitude!=null?r.gps.latitude:'',r.gps&&r.gps.longitude!=null?r.gps.longitude:'',r.telemetry_age_seconds??'',r.reported_at||'']);const csv=[head].concat(rows).map(row=>row.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(',')).join('\r\n');const blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='Volvo_Fleet_'+val('volvo_from')+'_to_'+val('volvo_to')+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}

function volvoGpsOk(g){return g&&Number.isFinite(Number(g.latitude))&&Number.isFinite(Number(g.longitude))&&Math.abs(Number(g.latitude))<=90&&Math.abs(Number(g.longitude))<=180;}
function volvoMedian(values){const a=(values||[]).filter(Number.isFinite).slice().sort((x,y)=>x-y);if(!a.length)return null;const m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2;}
function volvoGeoKm(a,b){const R=6371,dLat=(Number(b.latitude)-Number(a.latitude))*Math.PI/180,dLon=(Number(b.longitude)-Number(a.longitude))*Math.PI/180,lat1=Number(a.latitude)*Math.PI/180,lat2=Number(b.latitude)*Math.PI/180,s=Math.sin(dLat/2)**2+Math.cos(lat1)*Math.cos(lat2)*Math.sin(dLon/2)**2;return 2*R*Math.atan2(Math.sqrt(s),Math.sqrt(Math.max(0,1-s)));}
function volvoMainCluster(points){
  if(!points||points.length<3)return{points:points||[],outliers:[]};
  const center={latitude:volvoMedian(points.map(x=>Number(x.gps.latitude))),longitude:volvoMedian(points.map(x=>Number(x.gps.longitude)))};
  const distances=points.map(x=>({row:x,km:volvoGeoKm(center,x.gps)})),med=volvoMedian(distances.map(x=>x.km))||0;
  const limit=Math.max(8,Math.min(60,med*6+5));
  let main=distances.filter(x=>x.km<=limit).map(x=>x.row),out=distances.filter(x=>x.km>limit).map(x=>x.row);
  if(main.length<Math.ceil(points.length*.6)){main=points;out=[];}
  return{points:main,outliers:out};
}
function volvoLocationSummary(fleet,zones){
  fleet=fleet||[];zones=zones||[];
  const counts={};fleet.forEach(r=>{const k=r.location_name||'Transit / outside zones';counts[k]=(counts[k]||0)+1;});
  const chips=Object.keys(counts).sort((a,b)=>counts[b]-counts[a]).map(k=>'<button class="volvo-location-chip" type="button" title="Filter by location" onclick="volvoSelectLocationByName(decodeURIComponent(\''+encodeURIComponent(k)+'\'))"><b>'+esc(counts[k])+'</b>'+esc(k)+'</button>').join('');
  if(!zones.length)return '<div class="volvo-location-summary warning"><b>Location names are not configured yet.</b> GPS is working, but Pit / Crusher / Screening / WB / Stock / Dump names require one-time zone setup from <b>Configure locations</b>.</div>';
  return '<div class="volvo-location-summary"><span class="title">Current truck locations</span>'+chips+'</div>';
}
function volvoSelectLocationByName(name){
  const sel=document.getElementById('volvo_location');if(!sel)return;
  const options=[...sel.options],hit=options.find(o=>o.textContent.split(' · ')[0]===name);
  sel.value=hit?hit.value:(name==='Transit / outside zones'?'UNASSIGNED':'ALL');
  loadVolvoDashboard();
}
function volvoWorld(lat,lon,z){const size=256*Math.pow(2,z),clat=Math.max(-85.05112878,Math.min(85.05112878,Number(lat))),sin=Math.sin(clat*Math.PI/180);return{x:(Number(lon)+180)/360*size,y:(.5-Math.log((1+sin)/(1-sin))/(4*Math.PI))*size,size:size};}
function volvoWorldToLatLon(x,y,z){const size=256*Math.pow(2,z),lon=x/size*360-180,n=Math.PI-2*Math.PI*y/size,lat=180/Math.PI*Math.atan(.5*(Math.exp(n)-Math.exp(-n)));return{lat:lat,lon:lon};}
function volvoFit(points,w,h){if(points.length===1)return{lat:Number(points[0].gps.latitude),lon:Number(points[0].gps.longitude),z:17};for(let z=18;z>=3;z--){const pp=points.map(p=>volvoWorld(p.gps.latitude,p.gps.longitude,z)),xs=pp.map(p=>p.x),ys=pp.map(p=>p.y);if(Math.max(...xs)-Math.min(...xs)<w-120&&Math.max(...ys)-Math.min(...ys)<h-120){const cx=(Math.max(...xs)+Math.min(...xs))/2,cy=(Math.max(...ys)+Math.min(...ys))/2,ll=volvoWorldToLatLon(cx,cy,z);return{lat:ll.lat,lon:ll.lon,z:z};}}return{lat:Number(points[0].gps.latitude),lon:Number(points[0].gps.longitude),z:3};}
function renderVolvoMap(fleet,preserve){const box=document.getElementById('volvo_map');if(!box)return;const points=(fleet||[]).filter(r=>volvoGpsOk(r.gps));if(!points.length){box.innerHTML='<div class="volvo-map-error"><div><b>No GPS coordinates available</b><br><span>Vehicle telemetry will appear here when Volvo returns valid positions.</span></div></div>';return;}const cluster=volvoMainCluster(points);requestAnimationFrame(()=>{if(!preserve||!VOLVO.map){const fit=volvoFit(cluster.points,box.clientWidth||800,box.clientHeight||430);VOLVO.map={points:points,fitPoints:cluster.points,outliers:cluster.outliers,lat:fit.lat,lon:fit.lon,z:fit.z};}else{VOLVO.map.points=points;VOLVO.map.fitPoints=cluster.points;VOLVO.map.outliers=cluster.outliers;}drawVolvoMap();});}
function drawVolvoMap(){const box=document.getElementById('volvo_map'),m=VOLVO.map;if(!box||!m)return;const w=box.clientWidth||800,h=box.clientHeight||430,c=volvoWorld(m.lat,m.lon,m.z),left=c.x-w/2,top=c.y-h/2,n=Math.pow(2,m.z);let tiles='';for(let tx=Math.floor(left/256);tx<=Math.floor((left+w)/256);tx++){for(let ty=Math.floor(top/256);ty<=Math.floor((top+h)/256);ty++){if(ty<0||ty>=n)continue;const wrapped=((tx%n)+n)%n;const tileVersion=(VOLVO.mapStyle==='satellite'?'sat-r10':'street-r1');tiles+='<img class="volvo-map-tile" alt="" draggable="false" src="/api/volvo/map-tile/'+m.z+'/'+wrapped+'/'+ty+'.png?layer='+encodeURIComponent(VOLVO.mapStyle||'street')+'&v='+tileVersion+'" style="left:'+(tx*256-left)+'px;top:'+(ty*256-top)+'px">';}}
  let routeSvg='';if(VOLVO.route&&VOLVO.route.points&&VOLVO.route.points.length){const rp=VOLVO.route.points.map(p=>{const wpt=volvoWorld(p.latitude,p.longitude,m.z);return{x:wpt.x-left,y:wpt.y-top};});const poly=rp.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' ');const first=rp[0],last=rp[rp.length-1];routeSvg='<svg class="volvo-route-layer" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none"><polyline class="route-halo" points="'+poly+'"/><polyline class="route-main" points="'+poly+'"/><polyline class="route-hit" points="'+poly+'"/><circle class="route-start" cx="'+first.x+'" cy="'+first.y+'" r="7"/><text class="route-label start" x="'+(first.x+10)+'" y="'+(first.y-10)+'">START</text><circle class="route-end" cx="'+last.x+'" cy="'+last.y+'" r="7"/><text class="route-label end" x="'+(last.x+10)+'" y="'+(last.y-10)+'">END</text></svg>';}
  const zones=((VOLVO.data&&VOLVO.data.location_zones)||[]).map(z=>{const p=volvoWorld(z.latitude,z.longitude,m.z),x=p.x-left,y=p.y-top,mpp=156543.03392*Math.cos(Number(z.latitude)*Math.PI/180)/Math.pow(2,m.z),radius=Math.max(8,Number(z.radius_m||300)/Math.max(mpp,.01));return '<div class="volvo-zone" style="left:'+x+'px;top:'+y+'px;width:'+(radius*2)+'px;height:'+(radius*2)+'px"><span>'+esc(z.location_name)+'</span></div>';}).join('');
  const showLabels=VOLVO.labels||m.z>=16;
  const markerRows=(VOLVO.route&&!VOLVO.showFleetMarkers)?m.points.filter(r=>r.vin===VOLVO.selectedVin):m.points;
  const markers=markerRows.map(r=>{const i=m.points.findIndex(x=>x.vin===r.vin),p=volvoWorld(r.gps.latitude,r.gps.longitude,m.z),x=p.x-left,y=p.y-top,sel=VOLVO.selectedVin===r.vin?' selected':'',op=r.operational?' operational':'',loc=r.location_id?' · '+r.location_name:'';return '<button class="volvo-map-marker '+String(r.state||'').toLowerCase()+sel+op+(VOLVO.route?' route-mode':'')+'" style="left:'+x+'px;top:'+y+'px" aria-label="'+esc(r.name||r.vin)+'" onclick="showVolvoMapPopup('+i+',this)"><i></i><span class="volvo-map-label '+(showLabels||sel?'visible':'')+'">'+esc((r.name||r.machine_id||r.vin.slice(-6))+loc)+'</span></button>';}).join('');
  const attribution=VOLVO.mapStyle==='satellite'?'Satellite imagery © Esri and imagery providers':'© OpenStreetMap contributors';
  const outlierCount=(m.outliers||[]).length;box.innerHTML='<div class="volvo-map-tiles '+(VOLVO.mapStyle==='satellite'?'satellite':'street')+'">'+tiles+'</div><div class="volvo-zone-layer">'+zones+'</div>'+routeSvg+'<div class="volvo-map-markers">'+markers+'</div><div class="volvo-map-controls"><button onclick="volvoMapZoom(1)" title="Zoom in">+</button><button onclick="volvoMapZoom(-1)" title="Zoom out">−</button><button onclick="volvoFitFleet()" title="Fit fleet">⌂</button><button onclick="toggleVolvoLabels()" title="Toggle truck labels">L</button><button onclick="clearVolvoRoute()" title="Clear route">×</button></div><div class="volvo-map-note">'+esc(m.points.length)+' GPS trucks · '+esc(((VOLVO.data&&VOLVO.data.location_zones)||[]).length)+' zones'+(outlierCount?' · <b>'+esc(outlierCount)+' GPS outlier'+(outlierCount>1?'s':'')+' ignored in fit</b>':'')+' · '+esc(attribution)+'</div>';
  bindVolvoMapPan(box);
  bindVolvoRouteHover(box);
  if(VOLVO.popupVin){const idx=m.points.findIndex(r=>r.vin===VOLVO.popupVin),buttons=box.querySelectorAll('.volvo-map-marker');if(idx>=0&&buttons[idx])showVolvoMapPopup(idx,buttons[idx],true);}
}
function volvoDuration(seconds){
  const s=Math.max(0,Number(seconds)||0),h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=Math.round(s%60);
  if(h)return h+'h '+m+'m';
  if(m)return m+'m '+sec+'s';
  return sec+'s';
}
function bindVolvoRouteHover(box){
  const hit=box&&box.querySelector('.route-hit');
  if(!hit||!VOLVO.route||!VOLVO.route.points||!VOLVO.route.points.length)return;
  hit.onpointermove=function(e){
    const rect=box.getBoundingClientRect(),mx=e.clientX-rect.left,my=e.clientY-rect.top,m=VOLVO.map;
    const w=box.clientWidth||800,h=box.clientHeight||430,c=volvoWorld(m.lat,m.lon,m.z),left=c.x-w/2,top=c.y-h/2;
    let best=null,bestD=Infinity;
    const pts=VOLVO.route.points||[],step=Math.max(1,Math.floor(pts.length/700));
    for(let i=0;i<pts.length;i+=step){
      const wp=volvoWorld(pts[i].latitude,pts[i].longitude,m.z),x=wp.x-left,y=wp.y-top,d=(x-mx)*(x-mx)+(y-my)*(y-my);
      if(d<bestD){bestD=d;best={p:pts[i],x:x,y:y};}
    }
    if(!best||bestD>900){hideVolvoRouteHover(box);return;}
    showVolvoRouteHover(box,best.p,mx,my);
  };
  hit.onpointerleave=function(){hideVolvoRouteHover(box);};
}
function showVolvoRouteHover(box,p,x,y){
  let tip=box.querySelector('.volvo-route-hover');
  if(!tip){tip=document.createElement('div');tip.className='volvo-route-hover';box.appendChild(tip);}
  const speed=p.speed_kmh==null?'—':volvoNum(p.speed_kmh,1)+' km/h';
  const stop=Number(p.stop_seconds)||0;
  const rpm=p.engine_speed_rpm==null?'—':volvoNum(p.engine_speed_rpm,0)+' rpm';
  const fuel=p.fuel_used_l==null?'—':volvoNum(p.fuel_used_l,2)+' L';
  tip.innerHTML='<div class="title">'+esc(volvoDate(p.reported_at))+'</div>'+
    '<div class="grid">'+
      '<span>Speed<b>'+esc(speed)+'</b></span>'+
      '<span>Segment<b>'+esc(volvoNum(p.segment_km,3))+' km</b></span>'+
      '<span>Distance<b>'+esc(volvoNum(p.cumulative_km,2))+' km</b></span>'+
      '<span>Elapsed<b>'+esc(volvoDuration(p.elapsed_seconds))+'</b></span>'+
      '<span>Stopped<b class="'+(stop>=120?'warn':'')+'">'+esc(volvoDuration(stop))+'</b></span>'+
      '<span>Fuel used<b>'+esc(fuel)+'</b></span>'+
      '<span>Engine<b>'+esc(rpm)+'</b></span>'+
      '<span>Driver<b>'+esc(p.driver_id||'—')+'</b></span>'+
    '</div>'+
    '<div class="coords">'+esc(volvoNum(p.latitude,6))+', '+esc(volvoNum(p.longitude,6))+'</div>';
  tip.style.left=Math.max(8,Math.min((box.clientWidth||800)-220,x+14))+'px';
  tip.style.top=Math.max(8,Math.min((box.clientHeight||430)-170,y+14))+'px';
  tip.hidden=false;
}
function hideVolvoRouteHover(box){const tip=box&&box.querySelector('.volvo-route-hover');if(tip)tip.hidden=true;}
function setVolvoMapStyle(style){
  VOLVO.mapStyle=style==='satellite'?'satellite':'street';
  const a=document.getElementById('volvo_map_street'),b=document.getElementById('volvo_map_satellite');
  if(a){a.classList.toggle('primary',VOLVO.mapStyle==='street');a.classList.toggle('secondary',VOLVO.mapStyle!=='street');}
  if(b){b.classList.toggle('primary',VOLVO.mapStyle==='satellite');b.classList.toggle('secondary',VOLVO.mapStyle!=='satellite');}
  if(VOLVO.map)drawVolvoMap();
}
function toggleVolvoFleetMarkers(){
  VOLVO.showFleetMarkers=!VOLVO.showFleetMarkers;
  const b=document.getElementById('volvo_fleet_marker_btn');if(b)b.textContent=VOLVO.showFleetMarkers?'Hide trucks':'Show trucks';
  if(VOLVO.map)drawVolvoMap();
}
function toggleVolvoMapFullscreen(){
  const panel=document.getElementById('volvo_map_panel');if(!panel)return;
  if(document.fullscreenElement){document.exitFullscreen().catch(()=>{});return;}
  if(panel.requestFullscreen){panel.requestFullscreen().catch(()=>{panel.classList.toggle('volvo-map-fullscreen');setTimeout(()=>drawVolvoMap(),80);});}
  else{panel.classList.toggle('volvo-map-fullscreen');setTimeout(()=>drawVolvoMap(),80);}
}
document.addEventListener('fullscreenchange',()=>{const b=document.getElementById('volvo_fullscreen_btn');if(b)b.textContent=document.fullscreenElement?'Exit full screen':'Full screen';setTimeout(()=>{if(VOLVO.map)drawVolvoMap();},80);});
function toggleVolvoLabels(){VOLVO.labels=!VOLVO.labels;if(VOLVO.map)drawVolvoMap();}
function volvoFitLocation(){
  const id=val('volvo_location')||'ALL';
  const zones=(VOLVO.data&&VOLVO.data.location_zones)||[];
  const z=zones.find(x=>x.location_id===id);
  if(!z){volvoFitFleet();return;}
  VOLVO.map=VOLVO.map||{points:(VOLVO.data&&VOLVO.data.fleet)||[],lat:z.latitude,lon:z.longitude,z:16};
  VOLVO.map.lat=Number(z.latitude);VOLVO.map.lon=Number(z.longitude);
  const radius=Math.max(50,Number(z.radius_m)||300);
  VOLVO.map.z=radius<=150?18:radius<=300?17:radius<=600?16:radius<=1200?15:14;
  drawVolvoMap();
}
async function toggleVolvoZoneEditor(){
  VOLVO.zoneEditor=!VOLVO.zoneEditor;
  const box=document.getElementById('volvo_zone_editor');if(!box)return;
  box.hidden=!VOLVO.zoneEditor;
  if(!VOLVO.zoneEditor)return;
  box.innerHTML='<div class="loading">Loading TIOM locations…</div>';
  try{
    const data=await volvoRequest('location-zones');
    renderVolvoZoneEditor(data);
  }catch(e){box.innerHTML='<div class="bad">'+esc(e.message)+'</div>';}
}
function renderVolvoZoneEditor(data){
  const box=document.getElementById('volvo_zone_editor');if(!box)return;
  const zones=data.zones||[],available=data.available||[];
  const rows=zones.map(z=>'<div class="volvo-zone-row"><b>'+esc(z.location_name)+'</b><span>'+esc(volvoNum(z.latitude,6))+', '+esc(volvoNum(z.longitude,6))+' · '+esc(volvoNum(z.radius_m,0))+' m</span><button class="btn secondary small" onclick="editVolvoZone(\''+esc(z.location_id)+'\')">Edit</button><button class="btn secondary small" onclick="deleteVolvoZone(\''+esc(z.location_id)+'\')">Delete</button></div>').join('');
  const opts=available.map(x=>'<option value="'+esc(x.id)+'">'+esc(x.name)+(x.type?' · '+esc(x.type):'')+'</option>').join('');
  box.innerHTML='<div class="volvo-zone-form"><label>TIOM location<select id="volvo_zone_location">'+opts+'</select></label><label>Latitude<input id="volvo_zone_lat" type="number" step="0.000001"></label><label>Longitude<input id="volvo_zone_lon" type="number" step="0.000001"></label><label>Radius m<input id="volvo_zone_radius" type="number" min="50" max="5000" value="300"></label><div class="volvo-zone-actions"><button class="btn secondary small" onclick="useVolvoMapCenter()">Use map center</button><button class="btn secondary small" onclick="useSelectedVolvoTruck()">Use selected truck</button><button class="btn primary small" onclick="saveVolvoZone()">Save zone</button></div></div><div class="volvo-zone-list">'+(rows||'<div class="volvo-empty">No GPS location zones configured yet.</div>')+'</div>';
}
function useVolvoMapCenter(){if(!VOLVO.map)return;document.getElementById('volvo_zone_lat').value=Number(VOLVO.map.lat).toFixed(6);document.getElementById('volvo_zone_lon').value=Number(VOLVO.map.lon).toFixed(6);}
function useSelectedVolvoTruck(){
  const vin=VOLVO.popupVin||VOLVO.selectedVin;
  const r=((VOLVO.data&&VOLVO.data.fleet)||[]).find(x=>x.vin===vin);
  if(!r||!volvoGpsOk(r.gps)){toast('Click a truck marker with GPS first.',true);return;}
  document.getElementById('volvo_zone_lat').value=Number(r.gps.latitude).toFixed(6);
  document.getElementById('volvo_zone_lon').value=Number(r.gps.longitude).toFixed(6);
}
async function editVolvoZone(id){
  const z=((VOLVO.data&&VOLVO.data.location_zones)||[]).find(x=>x.location_id===id);
  if(!z)return;
  const sel=document.getElementById('volvo_zone_location');if(sel)sel.value=id;
  document.getElementById('volvo_zone_lat').value=z.latitude;
  document.getElementById('volvo_zone_lon').value=z.longitude;
  document.getElementById('volvo_zone_radius').value=z.radius_m;
}
async function saveVolvoZone(){
  const body={location_id:val('volvo_zone_location'),latitude:Number(val('volvo_zone_lat')),longitude:Number(val('volvo_zone_lon')),radius_m:Number(val('volvo_zone_radius')||300)};
  if(!body.location_id||!Number.isFinite(body.latitude)||!Number.isFinite(body.longitude)){toast('Choose a location and set valid map coordinates.',true);return;}
  try{await volvoRequest('location-zones',body);toast('Location zone saved.');await loadVolvoDashboard();VOLVO.zoneEditor=false;const b=document.getElementById('volvo_zone_editor');if(b)b.hidden=true;}catch(e){toast(e.message,true);}
}
async function deleteVolvoZone(id){
  try{await NMTPLNet.json('/api/volvo/location-zones/'+encodeURIComponent(id),{method:'DELETE'});toast('Location zone removed.');await loadVolvoDashboard();}catch(e){toast(e.message,true);}
}
function bindVolvoMapPan(box){box.onpointerdown=function(e){if(e.target.closest('button'))return;const c=volvoWorld(VOLVO.map.lat,VOLVO.map.lon,VOLVO.map.z);VOLVO.drag={x:e.clientX,y:e.clientY,cx:c.x,cy:c.y,pointerId:e.pointerId};try{box.setPointerCapture(e.pointerId);}catch(_e){}box.classList.add('dragging');};box.onpointermove=function(e){const d=VOLVO.drag;if(!d)return;const ll=volvoWorldToLatLon(d.cx-(e.clientX-d.x),d.cy-(e.clientY-d.y),VOLVO.map.z);VOLVO.map.lat=ll.lat;VOLVO.map.lon=ll.lon;drawVolvoMap();};box.onpointerup=box.onpointercancel=function(){VOLVO.drag=null;box.classList.remove('dragging');};box.onwheel=function(e){e.preventDefault();volvoMapZoom(e.deltaY<0?1:-1);};}
function volvoMapZoom(delta){if(!VOLVO.map)return;VOLVO.map.z=Math.max(3,Math.min(18,VOLVO.map.z+delta));drawVolvoMap();}
function volvoFitFleet(){if(VOLVO.data)renderVolvoMap(VOLVO.data.fleet,false);}
function clearVolvoRoute(){VOLVO.route=null;VOLVO.routeSession=null;VOLVO.routeTripId=null;VOLVO.selectedVin=null;VOLVO.popupVin=null;VOLVO.showFleetMarkers=true;document.querySelectorAll('.volvo-map-popup,.volvo-route-hover').forEach(x=>x.remove());const b=document.getElementById('volvo_fleet_marker_btn');if(b)b.textContent='Hide trucks';const s=document.getElementById('volvo_route_summary');if(s)s.textContent='Route cleared. Click a truck to track it again.';if(VOLVO.map)drawVolvoMap();}
function showVolvoMapPopup(index,button,preserve){
  document.querySelectorAll('.volvo-map-popup').forEach(x=>x.remove());
  const r=VOLVO.map.points[index],box=document.getElementById('volvo_map'),pop=document.createElement('div');
  if(!preserve)VOLVO.popupVin=r.vin;
  pop.className='volvo-map-popup';
  const gps=r.gps||{},warnings=(r.active_telltales||[]).map(x=>x.name).slice(0,4).join(', ');
  pop.innerHTML='<b>'+esc(r.name||'Volvo truck')+(r.machine_id?' · '+esc(r.machine_id):'')+'</b><div class="volvo-popup-location">'+esc(r.location_name||'Transit / outside configured zones')+'</div><div class="sub"><strong>'+esc(volvoStateLabel(r.state))+'</strong> · '+esc(volvoNum(Math.max(Number(r.wheel_speed_kmh)||0,Number(r.gps_speed_kmh)||0),1))+' km/h<br>Fuel '+esc(volvoNum(r.fuel_level_pct,1))+'% · Engine '+esc(volvoNum(r.engine_hours,1))+' h · Driver '+esc(r.driver_id||'—')+'<br>GPS '+esc(volvoNum(gps.latitude,6))+', '+esc(volvoNum(gps.longitude,6))+'<br>Age '+esc(volvoAge(r.telemetry_age_seconds))+' · '+esc(volvoDate(gps.positionDateTime||r.reported_at))+(warnings?'<br>Alerts: '+esc(warnings):'')+'</div><div class="volvo-popup-actions"><button class="btn primary small" onclick="trackVolvo(\''+esc(r.vin)+'\')">Track route</button></div>';
  const br=button.getBoundingClientRect(),bb=box.getBoundingClientRect();
  pop.style.left=Math.max(130,Math.min(bb.width-130,br.left-bb.left+br.width/2))+'px';
  pop.style.top=Math.max(150,br.top-bb.top)+'px';
  box.appendChild(pop);
}

async function trackVolvo(vin){VOLVO.selectedVin=vin;VOLVO.popupVin=null;VOLVO.showFleetMarkers=false;document.querySelectorAll('.volvo-map-popup').forEach(x=>x.remove());const b=document.getElementById('volvo_fleet_marker_btn');if(b)b.textContent='Show trucks';await loadVolvoRoute(vin,false);}
function volvoClock(value){return value?new Date(value).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',hour12:true}):'—';}
function volvoTripOptionLabel(t,index,total){
  const state=t.is_current?'Current':(index===total-1?'Latest':'Trip');
  const day=t.operating_date?String(t.operating_date):'';
  const shift=t.shift?' · Shift '+t.shift:'';
  const flow=(t.source_name||t.destination_name)?' · '+(t.source_name||'?')+' → '+(t.destination_name||'?'):' · provisional GPS';
  const material=t.material_name?' · '+t.material_name:'';
  const qty=t.quantity_mt!=null?' · '+volvoNum(t.quantity_mt,1)+' t':'';
  return state+' '+t.trip_id+' · '+day+shift+' · '+volvoClock(t.start_at)+'–'+volvoClock(t.end_at)+' · '+volvoNum(t.distance_km,2)+' km'+flow+material+qty;
}
function setVolvoRouteSummary(route){
  const s=document.getElementById('volvo_route_summary');if(!s||!route)return;
  const session=VOLVO.routeSession||route,trips=session.trips||[],trip=route.selected_trip||null,pts=route.points||[];
  const first=pts.length?pts[0].reported_at:null,last=pts.length?pts[pts.length-1].reported_at:null;
  const options='<option value="FULL" '+(VOLVO.routeTripId==='FULL'?'selected':'')+'>Full session · '+volvoNum(session.route_km,2)+' km · '+esc(session.trip_count||0)+' '+(session.segmentation_mode==='TIOM_TRIP'?'TIOM trips':'GPS legs')+'</option>'+
    trips.slice().reverse().map(t=>'<option value="'+esc(t.trip_id)+'" '+(VOLVO.routeTripId===t.trip_id?'selected':'')+'>'+esc(volvoTripOptionLabel(t,trips.indexOf(t),trips.length))+'</option>').join('');
  const distance=trip?trip.distance_km:session.route_km;
  const duration=trip?trip.duration_seconds:((first&&last)?Math.max(0,(new Date(last)-new Date(first))/1000):null);
  const stop=trip?trip.stop_seconds:null;
  const fuel=trip?trip.fuel_l:null;
  const avg=trip?trip.avg_speed_kmh:null;
  const authoritative=session.segmentation_mode==='TIOM_TRIP';
  const flow=trip&&((trip.source_name||trip.destination_name))
    ?(authoritative?'TIOM Trip · ':'')+(trip.source_name||'?')+' → '+(trip.destination_name||'?')+(trip.material_name?' · '+trip.material_name:'')+(trip.quantity_mt!=null?' · '+volvoNum(trip.quantity_mt,1)+' t':'')
    :(trip?'GPS provisional · '+(trip.operating_date||'')+' · Shift '+(trip.shift||'—')+' · '+(trip.boundary_reason||'movement'):'Full session');
  s.innerHTML=
    '<div class="volvo-trip-toolbar"><label>Route view<select id="volvo_trip_select" onchange="selectVolvoTrip(this.value,true)">'+options+'</select></label><div class="trip-flow">'+esc(flow)+'</div></div>'+
    '<div class="volvo-route-stats">'+
      '<div><span>Truck</span><b>'+esc(route.name)+(route.machine_id?' · '+esc(route.machine_id):'')+'</b></div>'+
      '<div><span>Distance</span><b>'+esc(volvoNum(distance,2))+' km</b></div>'+
      '<div><span>Duration</span><b>'+esc(duration==null?'—':volvoDuration(duration))+'</b></div>'+
      '<div><span>Stop time</span><b>'+esc(stop==null?'—':volvoDuration(stop))+'</b></div>'+
      '<div><span>Fuel</span><b>'+esc(fuel==null?'—':volvoNum(fuel,2)+' L')+'</b></div>'+
      '<div><span>Avg speed</span><b>'+esc(avg==null?'—':volvoNum(avg,1)+' km/h')+'</b></div>'+
      '<div class="actions"><button class="btn secondary small" onclick="focusVolvoRoute()">Fit route</button><button class="btn secondary small" onclick="toggleVolvoFleetMarkers()">'+(VOLVO.showFleetMarkers?'Hide trucks':'Show trucks')+'</button><button class="btn secondary small" onclick="clearVolvoRoute()">Exit route</button></div>'+
    '</div>'+
    '<div class="volvo-route-note">'+esc(session.precision_note||'')+'</div>';
}
function selectVolvoTrip(id,fit){
  const session=VOLVO.routeSession;if(!session)return;
  let trip=null,points=session.points||[];
  if(id&&id!=='FULL'){
    trip=(session.trips||[]).find(t=>t.trip_id===id)||null;
    const filtered=points.filter(p=>p.trip_id===id);
    if(trip&&filtered.length>=2)points=filtered;else{trip=null;id='FULL';points=session.points||[];}
  }else{id='FULL';}
  VOLVO.routeTripId=id;
  VOLVO.route=Object.assign({},session,{
    points:points,
    route_km:trip?trip.distance_km:session.route_km,
    point_count:trip?trip.point_count:session.point_count,
    selected_trip:trip
  });
  setVolvoRouteSummary(VOLVO.route);
  if(fit)focusVolvoRoute();else if(VOLVO.map)drawVolvoMap();
}
function focusVolvoRoute(){
  if(!VOLVO.route||!VOLVO.route.points||!VOLVO.route.points.length)return;
  const fake=VOLVO.route.points.map(p=>({gps:p})),box=document.getElementById('volvo_map'),fit=volvoFit(fake,(box&&box.clientWidth)||800,(box&&box.clientHeight)||430);
  if(!VOLVO.map)return;VOLVO.map.lat=fit.lat;VOLVO.map.lon=fit.lon;VOLVO.map.z=fit.z;drawVolvoMap();
}
async function loadVolvoRoute(vin,silent){try{
  const previousTrip=(VOLVO.selectedVin===vin&&VOLVO.routeTripId)?VOLVO.routeTripId:null;
  const q=new URLSearchParams({from_date:val('volvo_from'),to_date:val('volvo_to'),shift:val('volvo_shift')||'ALL',limit:'1500'});
  const session=await volvoRequest('route/'+encodeURIComponent(vin)+'?'+q.toString());
  VOLVO.routeSession=session;VOLVO.selectedVin=vin;VOLVO.lastRouteLoad=Date.now();
  const validPrevious=previousTrip==='FULL'||(session.trips||[]).some(t=>t.trip_id===previousTrip);
  const defaultTrip=validPrevious?previousTrip:(session.current_trip_id||((session.trips||[]).length?(session.trips||[])[session.trips.length-1].trip_id:'FULL'));
  selectVolvoTrip(defaultTrip,false);
  if(VOLVO.route&&VOLVO.route.points&&VOLVO.route.points.length)focusVolvoRoute();
}catch(e){if(!silent)toast(e.message,true);}}
