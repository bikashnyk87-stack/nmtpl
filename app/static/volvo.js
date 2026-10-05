/* Volvo dashboard is intentionally isolated from TIOM operational writes. */
var VOLVO={data:null,map:null,route:null,selectedVin:null,popupVin:null,timer:null,live:true,lastRouteLoad:0,drag:null,labels:false,zoneEditor:false,mapStyle:'street'};

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
  VOLVO.route=null;VOLVO.selectedVin=null;VOLVO.map=null;
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
function resetVolvoFilters(){const t=(S.boot&&S.boot.today)||new Date().toISOString().slice(0,10);document.getElementById('volvo_from').value=volvoDay(t,-6);document.getElementById('volvo_to').value=t;document.getElementById('volvo_machine').value='ALL';document.getElementById('volvo_state').value='ALL';document.getElementById('volvo_location').value='ALL';document.getElementById('volvo_shift').value='ALL';document.getElementById('volvo_mapping').value='ALL';VOLVO.route=null;VOLVO.selectedVin=null;loadVolvoDashboard();}
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
    '<div class="volvo-grid volvo-main-grid"><div class="volvo-panel"><div class="volvo-panel-head"><h3>Live GPS Fleet Map</h3><div class="volvo-map-head-actions"><div class="volvo-basemap-toggle"><button id="volvo_map_street" class="btn small '+(VOLVO.mapStyle==='street'?'primary':'secondary')+'" onclick="setVolvoMapStyle(\'street\')">Map</button><button id="volvo_map_satellite" class="btn small '+(VOLVO.mapStyle==='satellite'?'primary':'secondary')+'" onclick="setVolvoMapStyle(\'satellite\')">Satellite</button></div><button class="btn secondary small" onclick="volvoFitFleet()">Fit fleet</button><button class="btn secondary small" onclick="volvoFitLocation()">Fit location</button>'+(d.can_map?'<button class="btn secondary small" onclick="toggleVolvoZoneEditor()">Configure locations</button>':'')+'</div></div><div class="volvo-map-legend"><span><i class="moving"></i>Moving</span><span><i class="idle"></i>Engine on / idle</span><span><i class="stopped"></i>Stationary</span><span><em></em>Location zone</span></div><div id="volvo_map" class="volvo-map-wrap"></div><div id="volvo_zone_editor" class="volvo-zone-editor" hidden></div><div id="volvo_route_summary" class="volvo-route-summary">Select a truck marker or Track button to display its GPS trail.</div></div>'+
    '<div class="volvo-panel"><div class="volvo-panel-head"><h3>Live status</h3><span>Operational ≠ moving now</span></div><div class="volvo-panel-body">'+status+'<div class="volvo-footnote"><b>Operational</b> means the truck has shown movement, engine activity, fuel use or distance increase during the current shift. <b>Moving now</b> is only the latest speed reading. This prevents loading/unloading trucks from being shown as stopped operationally.</div><div class="volvo-fresh-line">Freshest telemetry: <b id="volvo_kpi_fresh">'+esc(volvoAge(freshest))+'</b></div></div></div></div>'+
    '<div class="volvo-chart-grid volvo-chart-grid-simple" style="margin-top:14px">'+
      volvoChartPanel('Fuel by truck','Ranked consumption · litres',volvoBars(pv,'fuel_l',' L'))+
      volvoChartPanel('Engine hours by truck','Lollipop comparison · hours',volvoDotPlot(pv,'engine_h',' h'))+
      volvoChartPanel('Distance vs fuel','Each dot is one truck · km vs L',volvoScatter(pv,'distance_km','fuel_l'))+
      volvoChartPanel('Daily fuel trend','Selected period · litres',volvoAreaLine(daily,'fuel_l',' L'))+
    '</div>'+volvoFleetTable(d));
  renderVolvoMap(fleet,!!(silent&&VOLVO.map));
  if(VOLVO.route)setVolvoRouteSummary(VOLVO.route);
}

function volvoChartPanel(title,sub,body){return '<div class="volvo-panel"><div class="volvo-panel-head"><h3>'+esc(title)+'</h3><span>'+esc(sub)+'</span></div><div class="volvo-panel-body">'+body+'</div></div>';}
function volvoBars(rows,key,suffix){
  rows=(rows||[]).filter(x=>x[key]!==null&&x[key]!==undefined).slice().sort((a,b)=>Number(b[key])-Number(a[key])).slice(0,12);
  if(!rows.length)return '<div class="volvo-empty">Not enough history yet. The collector needs at least two saved readings inside the selected period/shift.</div>';
  const max=Math.max(...rows.map(x=>Number(x[key])||0),1);
  return '<div class="volvo-bars">'+rows.map(x=>'<div class="volvo-bar-row"><div class="volvo-bar-label" title="'+esc(x.label)+'">'+esc(x.label)+'</div><div class="volvo-bar-track"><div class="volvo-bar-fill" style="width:'+Math.max(1,(Number(x[key])||0)/max*100).toFixed(1)+'%"></div></div><div class="volvo-bar-value">'+esc(volvoNum(x[key],2)+suffix)+'</div></div>').join('')+'</div>';
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
function volvoWorld(lat,lon,z){const size=256*Math.pow(2,z),clat=Math.max(-85.05112878,Math.min(85.05112878,Number(lat))),sin=Math.sin(clat*Math.PI/180);return{x:(Number(lon)+180)/360*size,y:(.5-Math.log((1+sin)/(1-sin))/(4*Math.PI))*size,size:size};}
function volvoWorldToLatLon(x,y,z){const size=256*Math.pow(2,z),lon=x/size*360-180,n=Math.PI-2*Math.PI*y/size,lat=180/Math.PI*Math.atan(.5*(Math.exp(n)-Math.exp(-n)));return{lat:lat,lon:lon};}
function volvoFit(points,w,h){if(points.length===1)return{lat:Number(points[0].gps.latitude),lon:Number(points[0].gps.longitude),z:17};for(let z=18;z>=3;z--){const pp=points.map(p=>volvoWorld(p.gps.latitude,p.gps.longitude,z)),xs=pp.map(p=>p.x),ys=pp.map(p=>p.y);if(Math.max(...xs)-Math.min(...xs)<w-120&&Math.max(...ys)-Math.min(...ys)<h-120){const cx=(Math.max(...xs)+Math.min(...xs))/2,cy=(Math.max(...ys)+Math.min(...ys))/2,ll=volvoWorldToLatLon(cx,cy,z);return{lat:ll.lat,lon:ll.lon,z:z};}}return{lat:Number(points[0].gps.latitude),lon:Number(points[0].gps.longitude),z:3};}
function renderVolvoMap(fleet,preserve){const box=document.getElementById('volvo_map');if(!box)return;const points=(fleet||[]).filter(r=>volvoGpsOk(r.gps));if(!points.length){box.innerHTML='<div class="volvo-map-error"><div><b>No GPS coordinates available</b><br><span>Vehicle telemetry will appear here when Volvo returns valid positions.</span></div></div>';return;}requestAnimationFrame(()=>{if(!preserve||!VOLVO.map){const fit=volvoFit(points,box.clientWidth||800,box.clientHeight||430);VOLVO.map={points:points,lat:fit.lat,lon:fit.lon,z:fit.z};}else{VOLVO.map.points=points;}drawVolvoMap();});}
function drawVolvoMap(){const box=document.getElementById('volvo_map'),m=VOLVO.map;if(!box||!m)return;const w=box.clientWidth||800,h=box.clientHeight||430,c=volvoWorld(m.lat,m.lon,m.z),left=c.x-w/2,top=c.y-h/2,n=Math.pow(2,m.z);let tiles='';for(let tx=Math.floor(left/256);tx<=Math.floor((left+w)/256);tx++){for(let ty=Math.floor(top/256);ty<=Math.floor((top+h)/256);ty++){if(ty<0||ty>=n)continue;const wrapped=((tx%n)+n)%n;tiles+='<img class="volvo-map-tile" alt="" draggable="false" src="/api/volvo/map-tile/'+m.z+'/'+wrapped+'/'+ty+'.png?layer='+encodeURIComponent(VOLVO.mapStyle||'street')+'" style="left:'+(tx*256-left)+'px;top:'+(ty*256-top)+'px">';}}
  let routeSvg='';if(VOLVO.route&&VOLVO.route.points&&VOLVO.route.points.length){const rp=VOLVO.route.points.map(p=>{const wpt=volvoWorld(p.latitude,p.longitude,m.z);return{x:wpt.x-left,y:wpt.y-top};});const poly=rp.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' ');const first=rp[0],last=rp[rp.length-1];routeSvg='<svg class="volvo-route-layer" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none"><polyline points="'+poly+'"/><circle class="route-start" cx="'+first.x+'" cy="'+first.y+'" r="6"/><circle class="route-end" cx="'+last.x+'" cy="'+last.y+'" r="6"/></svg>';}
  const zones=((VOLVO.data&&VOLVO.data.location_zones)||[]).map(z=>{const p=volvoWorld(z.latitude,z.longitude,m.z),x=p.x-left,y=p.y-top,mpp=156543.03392*Math.cos(Number(z.latitude)*Math.PI/180)/Math.pow(2,m.z),radius=Math.max(8,Number(z.radius_m||300)/Math.max(mpp,.01));return '<div class="volvo-zone" style="left:'+x+'px;top:'+y+'px;width:'+(radius*2)+'px;height:'+(radius*2)+'px"><span>'+esc(z.location_name)+'</span></div>';}).join('');
  const showLabels=VOLVO.labels||m.z>=16;
  const markers=m.points.map((r,i)=>{const p=volvoWorld(r.gps.latitude,r.gps.longitude,m.z),x=p.x-left,y=p.y-top,sel=VOLVO.selectedVin===r.vin?' selected':'',op=r.operational?' operational':'';return '<button class="volvo-map-marker '+String(r.state||'').toLowerCase()+sel+op+'" style="left:'+x+'px;top:'+y+'px" aria-label="'+esc(r.name||r.vin)+'" onclick="showVolvoMapPopup('+i+',this)"><i></i><span class="volvo-map-label '+(showLabels||sel?'visible':'')+'">'+esc(r.name||r.machine_id||r.vin.slice(-6))+'</span></button>';}).join('');
  const attribution=VOLVO.mapStyle==='satellite'?'Satellite imagery © Esri and imagery providers':'© OpenStreetMap contributors';
  box.innerHTML='<div class="volvo-map-tiles '+(VOLVO.mapStyle==='satellite'?'satellite':'street')+'">'+tiles+'</div><div class="volvo-zone-layer">'+zones+'</div>'+routeSvg+'<div class="volvo-map-markers">'+markers+'</div><div class="volvo-map-controls"><button onclick="volvoMapZoom(1)" title="Zoom in">+</button><button onclick="volvoMapZoom(-1)" title="Zoom out">−</button><button onclick="volvoFitFleet()" title="Fit fleet">⌂</button><button onclick="toggleVolvoLabels()" title="Toggle truck labels">L</button><button onclick="clearVolvoRoute()" title="Clear route">×</button></div><div class="volvo-map-note">'+esc(m.points.length)+' trucks · '+esc(((VOLVO.data&&VOLVO.data.location_zones)||[]).length)+' zones · '+esc(attribution)+'</div>';
  bindVolvoMapPan(box);
  if(VOLVO.popupVin){const idx=m.points.findIndex(r=>r.vin===VOLVO.popupVin),buttons=box.querySelectorAll('.volvo-map-marker');if(idx>=0&&buttons[idx])showVolvoMapPopup(idx,buttons[idx],true);}
}
function setVolvoMapStyle(style){
  VOLVO.mapStyle=style==='satellite'?'satellite':'street';
  const a=document.getElementById('volvo_map_street'),b=document.getElementById('volvo_map_satellite');
  if(a){a.classList.toggle('primary',VOLVO.mapStyle==='street');a.classList.toggle('secondary',VOLVO.mapStyle!=='street');}
  if(b){b.classList.toggle('primary',VOLVO.mapStyle==='satellite');b.classList.toggle('secondary',VOLVO.mapStyle!=='satellite');}
  if(VOLVO.map)drawVolvoMap();
}
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
function clearVolvoRoute(){VOLVO.route=null;VOLVO.selectedVin=null;VOLVO.popupVin=null;const s=document.getElementById('volvo_route_summary');if(s)s.textContent='Route cleared. Click a truck to track it again.';if(VOLVO.map)drawVolvoMap();}
function showVolvoMapPopup(index,button,preserve){
  document.querySelectorAll('.volvo-map-popup').forEach(x=>x.remove());
  const r=VOLVO.map.points[index],box=document.getElementById('volvo_map'),pop=document.createElement('div');
  if(!preserve)VOLVO.popupVin=r.vin;
  pop.className='volvo-map-popup';
  const gps=r.gps||{},warnings=(r.active_telltales||[]).map(x=>x.name).slice(0,4).join(', ');
  pop.innerHTML='<b>'+esc(r.name||'Volvo truck')+(r.machine_id?' · '+esc(r.machine_id):'')+'</b><div class="sub"><strong>'+esc(r.state)+'</strong> · Wheel '+esc(volvoNum(r.wheel_speed_kmh,1))+' km/h · GPS '+esc(volvoNum(r.gps_speed_kmh,1))+' km/h<br>Fuel '+esc(volvoNum(r.fuel_level_pct,1))+'% · AdBlue '+esc(volvoNum(r.adblue_pct,1))+'% · Engine '+esc(volvoNum(r.engine_hours,1))+' h<br>Gross '+esc(volvoNum(r.gross_weight_kg,0))+' kg · Axles '+esc(volvoNum(r.axle_total_kg,0))+' kg<br>Driver '+esc(r.driver_id||'—')+' · Heading '+esc(volvoNum(r.heading,0))+'° · Alt '+esc(volvoNum(r.altitude_m,0))+' m<br><strong>GPS '+esc(volvoNum(gps.latitude,6))+', '+esc(volvoNum(gps.longitude,6))+'</strong><br>Age '+esc(volvoAge(r.telemetry_age_seconds))+' · '+esc(volvoDate(gps.positionDateTime||r.reported_at))+(warnings?'<br>Alerts: '+esc(warnings):'')+'</div><div class="volvo-popup-actions"><button class="btn primary small" onclick="trackVolvo(\''+esc(r.vin)+'\')">Track route</button></div>';
  const br=button.getBoundingClientRect(),bb=box.getBoundingClientRect();
  pop.style.left=Math.max(130,Math.min(bb.width-130,br.left-bb.left+br.width/2))+'px';
  pop.style.top=Math.max(150,br.top-bb.top)+'px';
  box.appendChild(pop);
}

async function trackVolvo(vin){VOLVO.selectedVin=vin;await loadVolvoRoute(vin,false);}
function setVolvoRouteSummary(route){const s=document.getElementById('volvo_route_summary');if(s&&route)s.innerHTML='<b>'+esc(route.name)+(route.machine_id?' · TIOM '+esc(route.machine_id):'')+'</b> · '+esc(route.point_count)+' GPS reports · '+esc(volvoNum(route.route_km,2))+' km GPS trail · Shift '+esc(route.shift)+'<br><span>'+esc(route.precision_note)+'</span>';}
async function loadVolvoRoute(vin,silent){try{const q=new URLSearchParams({from_date:val('volvo_from'),to_date:val('volvo_to'),shift:val('volvo_shift')||'ALL',limit:'1500'});const route=await volvoRequest('route/'+encodeURIComponent(vin)+'?'+q.toString());VOLVO.route=route;VOLVO.selectedVin=vin;VOLVO.lastRouteLoad=Date.now();setVolvoRouteSummary(route);if(route.points&&route.points.length){const fake=route.points.map(p=>({gps:p})),box=document.getElementById('volvo_map'),fit=volvoFit(fake,(box&&box.clientWidth)||800,(box&&box.clientHeight)||430);if(!VOLVO.map)VOLVO.map={points:(VOLVO.data&&VOLVO.data.fleet)||[],lat:fit.lat,lon:fit.lon,z:fit.z};else{VOLVO.map.lat=fit.lat;VOLVO.map.lon=fit.lon;VOLVO.map.z=fit.z;}drawVolvoMap();}}catch(e){if(!silent)toast(e.message,true);}}
