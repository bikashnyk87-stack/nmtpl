/* Volvo dashboard is intentionally isolated from TIOM operational writes. */
var VOLVO={data:null,map:null,route:null,selectedVin:null,popupVin:null,timer:null,live:true,lastRouteLoad:0,drag:null};

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

function renderVolvo(){
  const today=(S.boot&&S.boot.today)||new Date().toISOString().slice(0,10),from=volvoDay(today,-6);
  if(VOLVO.timer){clearInterval(VOLVO.timer);VOLVO.timer=null;}
  VOLVO.route=null;VOLVO.selectedVin=null;VOLVO.map=null;
  html('app','<div class="volvo-shell">'+
    '<div class="panel volvo-hero"><div><div class="eyebrow">VOLVO CONNECTED FLEET</div><h2>Truck Telemetry Command Center</h2><p>GPS · route trail · fuel · utilization · load · health</p><div class="volvo-sync-pill"><span class="volvo-sync-dot"></span><span id="volvo_sync_text">Loading latest saved telemetry…</span></div></div>'+volvoTruckArt()+'</div>'+
    '<div class="panel volvo-filters">'+
      '<label>From date<input id="volvo_from" type="date" value="'+esc(from)+'"></label>'+
      '<label>To date<input id="volvo_to" type="date" value="'+esc(today)+'"></label>'+
      '<label>Truck / Machine<select id="volvo_machine"><option value="ALL">All Volvo trucks</option></select></label>'+
      '<label>Vehicle state<select id="volvo_state"><option value="ALL">All states</option><option>RUNNING</option><option>IDLE</option><option>STOPPED</option><option>OFFLINE</option></select></label>'+
      '<label>Shift<select id="volvo_shift"><option value="ALL">All shifts</option><option value="A">A · 06:00–14:00</option><option value="B">B · 14:00–22:00</option><option value="C">C · 22:00–06:00</option></select></label>'+
      '<label>Mapping<select id="volvo_mapping"><option value="ALL">Mapped + Unmapped</option><option value="MAPPED">Mapped only</option><option value="UNMAPPED">Unmapped only</option></select></label>'+
      '<div class="volvo-filter-actions"><button class="btn primary" onclick="loadVolvoDashboard()">Apply</button><button id="volvo_live_btn" class="btn secondary" onclick="toggleVolvoLive()">Live 30s: ON</button><button class="btn secondary" onclick="resetVolvoFilters()">Reset</button></div>'+
    '</div><div id="volvo_body"><div class="panel"><div class="loading">Loading Volvo dashboard…</div></div></div></div>');
  loadVolvoDashboard(true);
  VOLVO.timer=setInterval(function(){if(S.screen==='VOLVO'&&VOLVO.live)refreshVolvoLive();},30000);
}
function resetVolvoFilters(){const t=(S.boot&&S.boot.today)||new Date().toISOString().slice(0,10);document.getElementById('volvo_from').value=volvoDay(t,-6);document.getElementById('volvo_to').value=t;document.getElementById('volvo_machine').value='ALL';document.getElementById('volvo_state').value='ALL';document.getElementById('volvo_shift').value='ALL';document.getElementById('volvo_mapping').value='ALL';VOLVO.route=null;VOLVO.selectedVin=null;loadVolvoDashboard();}
function toggleVolvoLive(){VOLVO.live=!VOLVO.live;const b=document.getElementById('volvo_live_btn');if(b)b.textContent='Live 30s: '+(VOLVO.live?'ON':'OFF');}
function volvoQuery(){return new URLSearchParams({from_date:val('volvo_from'),to_date:val('volvo_to'),vehicle:val('volvo_machine')||'ALL',state:val('volvo_state')||'ALL',shift:val('volvo_shift')||'ALL',mapping:val('volvo_mapping')||'ALL'}).toString();}

async function loadVolvoDashboard(first,silent){
  try{
    const currentVehicle=val('volvo_machine')||'ALL',data=await volvoRequest('dashboard?'+volvoQuery());
    if(S.screen!=='VOLVO')return;VOLVO.data=data;
    const sync=document.getElementById('volvo_sync_text');if(sync)sync.textContent='Last collection: '+volvoDate(data.last_sync)+' · dashboard auto-refresh '+(VOLVO.live?'ON':'OFF');
    const machine=document.getElementById('volvo_machine'),vehicles=((data.filters&&data.filters.vehicles)||[]);
    if(first||machine.options.length!==vehicles.length+1){machine.innerHTML='<option value="ALL">All Volvo trucks</option>'+vehicles.map(x=>'<option value="'+esc(x.vin)+'">'+esc(x.label)+' · '+esc(x.vin.slice(-6))+'</option>').join('');machine.value=vehicles.some(x=>x.vin===currentVehicle)?currentVehicle:'ALL';}
    renderVolvoDashboardBody(data,!!silent);
    if(VOLVO.selectedVin&&VOLVO.live&&(Date.now()-VOLVO.lastRouteLoad>60000))loadVolvoRoute(VOLVO.selectedVin,true);
  }catch(e){if(S.screen==='VOLVO'&&!silent)html('volvo_body','<div class="panel bad">'+esc(e.message)+'</div>');}
}

function volvoApplyLiveFilters(rows){
  const vehicle=val('volvo_machine')||'ALL',state=val('volvo_state')||'ALL',mapping=val('volvo_mapping')||'ALL';
  return (rows||[]).filter(r=>{
    if(vehicle!=='ALL'&&![r.vin,r.machine_id,r.name].includes(vehicle))return false;
    if(state!=='ALL'&&r.state!==state)return false;
    if(mapping==='MAPPED'&&!r.machine_id)return false;
    if(mapping==='UNMAPPED'&&r.machine_id)return false;
    return true;
  });
}
function updateVolvoLiveKpis(fleet){
  const counts={RUNNING:0,IDLE:0,STOPPED:0,OFFLINE:0};fleet.forEach(r=>{if(counts[r.state]!==undefined)counts[r.state]++;});
  const cards=document.querySelectorAll('.volvo-kpis .volvo-kpi b');
  const freshest=fleet.map(x=>Number(x.telemetry_age_seconds)).filter(Number.isFinite).sort((a,b)=>a-b)[0];
  const gps=fleet.filter(x=>volvoGpsOk(x.gps)).length;
  const values=[fleet.length,counts.RUNNING,counts.IDLE,counts.STOPPED,counts.OFFLINE];
  values.forEach((v,i)=>{if(cards[i])cards[i].textContent=String(v);});
  if(cards[12])cards[12].textContent=String(gps);
  if(cards[13])cards[13].textContent=volvoAge(freshest);
  const stateCards=document.querySelectorAll('.volvo-state-cards .volvo-state b');
  [counts.RUNNING,counts.IDLE,counts.STOPPED,counts.OFFLINE].forEach((v,i)=>{if(stateCards[i])stateCards[i].textContent=String(v);});
  if(VOLVO.data)VOLVO.data.state_counts=counts;
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
    VOLVO.data.fleet=fleet;VOLVO.data.last_sync=live.last_sync;VOLVO.data.equipment=live.equipment||VOLVO.data.equipment;VOLVO.data.can_map=!!live.can_map;
    const sync=document.getElementById('volvo_sync_text');if(sync)sync.textContent='Last collection: '+volvoDate(live.last_sync)+' · live fleet refresh '+(VOLVO.live?'ON':'OFF');
    updateVolvoLiveKpis(fleet);
    renderVolvoMap(fleet,true);
    refreshVolvoFleetTable();
    if(VOLVO.selectedVin&&(Date.now()-VOLVO.lastRouteLoad>60000))loadVolvoRoute(VOLVO.selectedVin,true);
  }catch(e){/* keep the last good dashboard visible if a live refresh fails */}
}

function renderVolvoDashboardBody(d,silent){
  const c=d.state_counts||{},t=d.totals||{},fleet=d.fleet||[],pv=d.period_vehicles||[],daily=d.daily||[];
  const freshest=fleet.map(x=>Number(x.telemetry_age_seconds)).filter(Number.isFinite).sort((a,b)=>a-b)[0];
  const kpis=[
    ['Fleet',fleet.length,'vehicles',''],['Running',c.RUNNING||0,'current','run'],['Idle',c.IDLE||0,'current','idle'],['Stopped',c.STOPPED||0,'current',''],['Offline',c.OFFLINE||0,'current','offline'],
    ['Engine hours',volvoNum(t.engine_h,1),'selected period',''],['Distance',volvoNum(t.distance_km,0)+' km','selected period',''],['Fuel used',volvoNum(t.fuel_l,0)+' L','selected period',''],['Idle fuel',volvoNum(t.idle_fuel_l,1)+' L','selected period','idle'],['Moving fuel',volvoNum(t.moving_fuel_l,1)+' L','selected period','run'],
    ['Avg fuel / hour',volvoNum(t.fuel_lph,2)+' L/h','selected period',''],['Fuel / 100 km',volvoNum(t.fuel_l_100km,2)+' L','selected period',''],['GPS available',fleet.filter(x=>volvoGpsOk(x.gps)).length,'latest position',''],['Freshest data',volvoAge(freshest),'telemetry age','']
  ].map(x=>'<div class="volvo-kpi '+x[3]+'"><span>'+esc(x[0])+'</span><b>'+esc(String(x[1]))+'</b><small>'+esc(x[2])+'</small></div>').join('');
  const state='<div class="volvo-state-cards"><div class="volvo-state running"><b>'+esc(c.RUNNING||0)+'</b><span>RUNNING</span></div><div class="volvo-state idle"><b>'+esc(c.IDLE||0)+'</b><span>IDLE</span></div><div class="volvo-state stopped"><b>'+esc(c.STOPPED||0)+'</b><span>STOPPED</span></div><div class="volvo-state offline"><b>'+esc(c.OFFLINE||0)+'</b><span>OFFLINE</span></div></div>';
  html('volvo_body','<div class="volvo-kpis">'+kpis+'</div>'+
    '<div class="volvo-grid"><div class="volvo-panel"><div class="volvo-panel-head"><h3>Live GPS Fleet Map</h3><span id="volvo_map_mode">Drag to pan · wheel/+− to zoom · click a truck</span></div><div id="volvo_map" class="volvo-map-wrap"></div><div id="volvo_route_summary" class="volvo-route-summary">Select a truck marker or Track button to display its saved GPS trail.</div></div><div class="volvo-panel"><div class="volvo-panel-head"><h3>Current Vehicle State</h3><span>'+esc(d.from_date)+' → '+esc(d.to_date)+' · Shift '+esc(d.shift||'ALL')+'</span></div><div class="volvo-panel-body">'+state+'<div class="volvo-footnote">RUNNING uses wheel/GPS speed. IDLE uses RPM when available and also recent engine-hour/fuel increase while distance stays nearly unchanged. OFFLINE means telemetry is older than 120 minutes. Period charts and route history follow the selected operating-date/shift filter.</div></div></div></div>'+
    '<div class="volvo-chart-grid" style="margin-top:14px">'+
      volvoChartPanel('Fuel consumption by truck','Period delta · litres',volvoBars(pv,'fuel_l',' L'))+
      volvoChartPanel('Distance travelled by truck','Period delta · km',volvoBars(pv,'distance_km',' km'))+
      volvoChartPanel('Engine hours by truck','Period delta · hours',volvoBars(pv,'engine_h',' h'))+
      volvoChartPanel('Fuel efficiency by truck','Period average · L/hour',volvoBars(pv,'fuel_lph',' L/h'))+
      volvoChartPanel('Idle fuel by truck','Period delta · litres',volvoBars(pv,'idle_fuel_l',' L'))+
      volvoChartPanel('Moving fuel by truck','Period delta · litres',volvoBars(pv,'moving_fuel_l',' L'))+
      volvoChartPanel('Daily fuel trend','Litres · data labels',volvoLine(daily,'fuel_l',' L'))+
      volvoChartPanel('Daily distance trend','Kilometres · data labels',volvoLine(daily,'distance_km',' km'))+
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
  const rows=(d.fleet||[]).map(r=>{const gps=volvoGpsOk(r.gps)?volvoNum(r.gps.latitude,6)+', '+volvoNum(r.gps.longitude,6):'—';let link=esc(r.machine_id||'Unmapped');
    if(d.can_map){const opts=(d.equipment||[]).map(e=>'<option value="'+esc(e.id)+'" '+(r.machine_id===e.id?'selected':'')+'>'+esc(e.label)+' ('+esc(e.id)+')</option>').join('');link='<div class="volvo-map-select"><select id="volvo_link_'+esc(r.vin)+'"><option value="">Unmapped</option>'+opts+'</select><button class="btn secondary small" data-vin="'+esc(r.vin)+'" onclick="saveVolvoLink(this)">Save</button></div>';}
    const warnings=(r.active_telltales||[]).map(x=>x.name).slice(0,3).join(', ');
    return '<tr><td><div class="volvo-machine">'+esc(r.name||r.vin)+'</div><div class="volvo-vin">'+esc(r.vin)+(r.machine_id?' · TIOM '+esc(r.machine_id):'')+'</div></td><td><span class="volvo-badge '+esc(r.state)+'">'+esc(r.state)+'</span></td><td><button class="btn secondary small" onclick="trackVolvo(\''+esc(r.vin)+'\')">Track</button></td><td>'+link+'</td><td>'+esc(volvoNum(r.wheel_speed_kmh,1))+'</td><td>'+esc(volvoNum(r.gps_speed_kmh,1))+'</td><td>'+esc(volvoNum(r.engine_speed_rpm,0))+'</td><td>'+esc(volvoNum(r.fuel_level_pct,1))+'</td><td>'+esc(volvoNum(r.adblue_pct,1))+'</td><td>'+esc(volvoNum(r.engine_hours,1))+'</td><td>'+esc(volvoNum(r.distance_km,1))+'</td><td>'+esc(volvoNum(r.fuel_used_l,1))+'</td><td>'+esc(volvoNum(r.idle_fuel_l,1))+'</td><td>'+esc(volvoNum(r.moving_fuel_l,1))+'</td><td>'+esc(volvoNum(r.gross_weight_kg,0))+'</td><td>'+esc(volvoNum(r.axle_total_kg,0))+'</td><td>'+esc(volvoNum(r.moving_h,1))+'</td><td>'+esc(volvoNum(r.stationary_h,1))+'</td><td>'+esc(r.driver_id||'—')+'</td><td>'+esc(volvoNum(r.service_distance_km,0))+'</td><td>'+esc(volvoNum(r.coolant_temp_c,1))+'</td><td title="'+esc(warnings)+'">'+esc(r.warning_count||0)+'</td><td>'+esc(gps)+'</td><td>'+esc(volvoAge(r.telemetry_age_seconds))+'</td><td>'+esc(volvoDate(r.reported_at))+'</td></tr>';
  }).join('');
  return '<div class="volvo-panel" style="margin-top:14px"><div class="volvo-panel-head"><h3>Volvo Fleet Detail</h3><div><button class="btn secondary small" onclick="volvoExportCsv()">Export CSV</button></div></div><div class="volvo-table-wrap"><table class="volvo-table"><thead><tr><th>Volvo truck / VIN</th><th>State</th><th>Route</th><th>TIOM link</th><th>Wheel km/h</th><th>GPS km/h</th><th>RPM</th><th>Fuel %</th><th>AdBlue %</th><th>Engine h</th><th>Odometer km</th><th>Total fuel L</th><th>Idle fuel L</th><th>Moving fuel L</th><th>Gross kg</th><th>Axle kg</th><th>Moving h</th><th>Stationary h</th><th>Driver</th><th>Service km</th><th>Coolant °C</th><th>Alerts</th><th>GPS</th><th>Age</th><th>Reported</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+(rows?'':'<div class="volvo-empty">No vehicles match these filters.</div>')+'</div>';
}
async function saveVolvoLink(btn){btn.disabled=true;try{const vin=btn.dataset.vin,machine=document.getElementById('volvo_link_'+vin).value||null;await volvoRequest('mapping',{vin:vin,machine_id:machine});toast('Volvo vehicle mapping saved.');await loadVolvoDashboard();}catch(e){toast(e.message,true);}finally{btn.disabled=false;}}
function volvoExportCsv(){if(!VOLVO.data)return;const head=['VolvoName','MachineID','VIN','State','WheelSpeedKmh','GpsSpeedKmh','EngineRPM','FuelLevelPct','AdBluePct','EngineHours','DistanceKm','TotalFuelL','IdleFuelL','MovingFuelL','GrossWeightKg','AxleTotalKg','MovingHours','StationaryHours','Driver','ServiceDistanceKm','CoolantC','WarningCount','Latitude','Longitude','TelemetryAgeSeconds','ReportedAt'];const rows=(VOLVO.data.fleet||[]).map(r=>[r.name||'',r.machine_id||'',r.vin,r.state,r.wheel_speed_kmh??'',r.gps_speed_kmh??'',r.engine_speed_rpm??'',r.fuel_level_pct??'',r.adblue_pct??'',r.engine_hours??'',r.distance_km??'',r.fuel_used_l??'',r.idle_fuel_l??'',r.moving_fuel_l??'',r.gross_weight_kg??'',r.axle_total_kg??'',r.moving_h??'',r.stationary_h??'',r.driver_id||'',r.service_distance_km??'',r.coolant_temp_c??'',r.warning_count??'',r.gps&&r.gps.latitude!=null?r.gps.latitude:'',r.gps&&r.gps.longitude!=null?r.gps.longitude:'',r.telemetry_age_seconds??'',r.reported_at||'']);const csv=[head].concat(rows).map(row=>row.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(',')).join('\r\n');const blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='Volvo_Fleet_'+val('volvo_from')+'_to_'+val('volvo_to')+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}

function volvoGpsOk(g){return g&&Number.isFinite(Number(g.latitude))&&Number.isFinite(Number(g.longitude))&&Math.abs(Number(g.latitude))<=90&&Math.abs(Number(g.longitude))<=180;}
function volvoWorld(lat,lon,z){const size=256*Math.pow(2,z),clat=Math.max(-85.05112878,Math.min(85.05112878,Number(lat))),sin=Math.sin(clat*Math.PI/180);return{x:(Number(lon)+180)/360*size,y:(.5-Math.log((1+sin)/(1-sin))/(4*Math.PI))*size,size:size};}
function volvoWorldToLatLon(x,y,z){const size=256*Math.pow(2,z),lon=x/size*360-180,n=Math.PI-2*Math.PI*y/size,lat=180/Math.PI*Math.atan(.5*(Math.exp(n)-Math.exp(-n)));return{lat:lat,lon:lon};}
function volvoFit(points,w,h){if(points.length===1)return{lat:Number(points[0].gps.latitude),lon:Number(points[0].gps.longitude),z:17};for(let z=18;z>=3;z--){const pp=points.map(p=>volvoWorld(p.gps.latitude,p.gps.longitude,z)),xs=pp.map(p=>p.x),ys=pp.map(p=>p.y);if(Math.max(...xs)-Math.min(...xs)<w-120&&Math.max(...ys)-Math.min(...ys)<h-120){const cx=(Math.max(...xs)+Math.min(...xs))/2,cy=(Math.max(...ys)+Math.min(...ys))/2,ll=volvoWorldToLatLon(cx,cy,z);return{lat:ll.lat,lon:ll.lon,z:z};}}return{lat:Number(points[0].gps.latitude),lon:Number(points[0].gps.longitude),z:3};}
function renderVolvoMap(fleet,preserve){const box=document.getElementById('volvo_map');if(!box)return;const points=(fleet||[]).filter(r=>volvoGpsOk(r.gps));if(!points.length){box.innerHTML='<div class="volvo-map-error"><div><b>No GPS coordinates available</b><br><span>Vehicle telemetry will appear here when Volvo returns valid positions.</span></div></div>';return;}requestAnimationFrame(()=>{if(!preserve||!VOLVO.map){const fit=volvoFit(points,box.clientWidth||800,box.clientHeight||430);VOLVO.map={points:points,lat:fit.lat,lon:fit.lon,z:fit.z};}else{VOLVO.map.points=points;}drawVolvoMap();});}
function drawVolvoMap(){const box=document.getElementById('volvo_map'),m=VOLVO.map;if(!box||!m)return;const w=box.clientWidth||800,h=box.clientHeight||430,c=volvoWorld(m.lat,m.lon,m.z),left=c.x-w/2,top=c.y-h/2,n=Math.pow(2,m.z);let tiles='';for(let tx=Math.floor(left/256);tx<=Math.floor((left+w)/256);tx++){for(let ty=Math.floor(top/256);ty<=Math.floor((top+h)/256);ty++){if(ty<0||ty>=n)continue;const wrapped=((tx%n)+n)%n;tiles+='<img class="volvo-map-tile" alt="" draggable="false" src="/api/volvo/map-tile/'+m.z+'/'+wrapped+'/'+ty+'.png" style="left:'+(tx*256-left)+'px;top:'+(ty*256-top)+'px">';}}
  let routeSvg='';if(VOLVO.route&&VOLVO.route.points&&VOLVO.route.points.length){const rp=VOLVO.route.points.map(p=>{const wpt=volvoWorld(p.latitude,p.longitude,m.z);return{x:wpt.x-left,y:wpt.y-top};});const poly=rp.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' ');const first=rp[0],last=rp[rp.length-1];routeSvg='<svg class="volvo-route-layer" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none"><polyline points="'+poly+'"/><circle class="route-start" cx="'+first.x+'" cy="'+first.y+'" r="6"/><circle class="route-end" cx="'+last.x+'" cy="'+last.y+'" r="6"/></svg>';}
  const markers=m.points.map((r,i)=>{const p=volvoWorld(r.gps.latitude,r.gps.longitude,m.z),x=p.x-left,y=p.y-top,sel=VOLVO.selectedVin===r.vin?' selected':'';return '<button class="volvo-map-marker '+String(r.state||'').toLowerCase()+sel+'" style="left:'+x+'px;top:'+y+'px" aria-label="'+esc(r.name||r.vin)+'" onclick="showVolvoMapPopup('+i+',this)"><i></i><span class="volvo-map-label">'+esc(r.name||r.machine_id||r.vin.slice(-6))+'</span></button>';}).join('');
  box.innerHTML='<div class="volvo-map-tiles">'+tiles+'</div>'+routeSvg+'<div class="volvo-map-markers">'+markers+'</div><div class="volvo-map-controls"><button onclick="volvoMapZoom(1)" title="Zoom in">+</button><button onclick="volvoMapZoom(-1)" title="Zoom out">−</button><button onclick="volvoFitFleet()" title="Fit fleet">⌂</button><button onclick="clearVolvoRoute()" title="Clear route">×</button></div><div class="volvo-map-note">© OpenStreetMap contributors · GNSS from Volvo API · drag map to pan</div>';
  bindVolvoMapPan(box);
  if(VOLVO.popupVin){const idx=m.points.findIndex(r=>r.vin===VOLVO.popupVin),buttons=box.querySelectorAll('.volvo-map-marker');if(idx>=0&&buttons[idx])showVolvoMapPopup(idx,buttons[idx],true);}
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
