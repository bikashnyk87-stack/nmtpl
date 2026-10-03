/* Transport and pilot shell around the retained v7.3 attendance/shift screens. */
async function request(path, body) {
  const options={};
  if(body!==undefined){options.method='POST';options.headers={'Content-Type':'application/json'};options.body=JSON.stringify(body);}
  try{return await NMTPLNet.json('/api/web/'+path,options)}
  catch(error){if(error.status===401){showLogin(false);text('login_status','Session expired. Please sign in again.')}throw error}
}
window.addEventListener('nmtpl-session-expired',()=>{showLogin(false);text('login_status','Session expired. Please sign in again.')});
function appRun(success, failure) {
  return new Proxy({}, {get: (_, method) => (...args) => request('rpc', {method, args})
    .then(result => {if (success) success(result);})
    .catch(error => {if (failure) failure(error); else toast(error.message, true);})});
}
function shiftOptions() { return opt(S.boot.masters.shifts, x=>x, x=>x, S.boot.shift); }
function setContext(d,s,t) {text('ctx', `${d} · ${s} Shift · ${t}`);}
function showLogin(setup) {
  S.boot=null; S.screen='LOGIN'; S.att=null; S.shiftCtl=null;
  document.getElementById('nav').hidden=true; document.getElementById('signOutBtn').hidden=true;
  text('ctx','--'); text('userName','--');
  html('app','<div class="panel login"><div class="eyebrow">NMTPL SERVER</div><h1>'+(setup?'Create administrator':'Operations MIS')+'</h1><p class="note">'+(setup?'Create your server account on this laptop. This does not change your Google webapp account.':'Sign in with your server account.')+'</p><form id="login_form">'+(setup?'<label>Your name<input id="login_name" maxlength="120" required autocomplete="name"></label>':'')+'<label>User ID<input id="login_id" required maxlength="60" pattern="[A-Za-z0-9_.-]+" autocomplete="username"></label><label>Password<input id="login_pw" type="password" required '+(setup?'minlength="12"':'')+' maxlength="128" autocomplete="'+(setup?'new-password':'current-password')+'"></label>'+(setup?'<p class="note">Use at least 12 characters.</p>':'')+'<button id="login_submit" class="btn primary">'+(setup?'Create account':'Sign in')+'</button><div id="login_status" role="alert"></div></form></div>');
  document.getElementById('login_form').onsubmit=async event=>{
    event.preventDefault(); const button=document.getElementById('login_submit'); button.disabled=true;
    text('login_status',setup?'Creating account…':'Signing in…');
    const body={loginId:val('login_id'),password:val('login_pw'),name:val('login_name')||'Administrator'};
    try {await request(setup?'setup':'login',body); await enterApp();}
    catch(error){text('login_status',error.message);button.disabled=false;}
  };
}
async function enterApp(){
  const boot=await request('rpc',{method:'getBootstrap',args:[]}); S.boot=boot;
  text('userName',boot.user.name);setContext(boot.today,boot.shift,boot.time);
  document.getElementById('signOutBtn').hidden=false;buildNav();render(boot.user.modules.includes('DASHBOARD')?'DASHBOARD':'HOME');
}
async function signOut(){const uid=S.boot?.user?.loginId;try{await request('logout',{})}finally{if(uid)NMTPLNet.clearUserDrafts(uid);if(typeof window.NMTPLClearTiomDrafts==='function')window.NMTPLClearTiomDrafts();showLogin(false)}}
function buildNav(){
  const items=[];
  if(S.boot.user.modules.includes('DASHBOARD'))items.push(['DASHBOARD','Dashboard']);
  for(const [id,label] of [['ATTENDANCE','Attendance'],['SHIFT_CONTROL','Shift Control'],['PRODUCTION','Production'],['WB','WB Upload'],['HSD','HSD'],['MASTERS','Masters']])if(S.boot.user.modules.includes(id))items.push([id,label]);
  if(S.boot.user.isManagement||S.boot.user.modules.includes('DASHBOARD'))items.push(['VOLVO','VOLVO']);
  items.push(['HOME','Overview']);
  if(S.boot.user.isManagement)items.push(['USERS','Users']);
  const nav=document.getElementById('nav');nav.hidden=false;
  nav.innerHTML=items.map(([id,label])=>'<button id="nav_'+id+'" onclick="render(\''+id+'\')">'+label+'</button>').join('');
}
function render(screen){
  S.screen=screen;document.querySelectorAll('#nav button').forEach(b=>b.classList.remove('active'));
  const button=document.getElementById('nav_'+screen);if(button)button.classList.add('active');
  ({VOLVO:renderVolvo,DASHBOARD:renderDashboard,HOME:renderHome,ATTENDANCE:renderAttendance,SHIFT_CONTROL:renderShiftControl,PRODUCTION:renderProduction,WB:renderWb,HSD:renderHsd,MASTERS:renderMasters,MECHANICAL:window.renderMechanical,USERS:renderUsers}[screen]||renderHome)();
  window.scrollTo(0,0);
}
function renderHome(){
  html('app','<div class="panel"><div class="eyebrow">SERVER PILOT</div><h1>Welcome, '+esc(S.boot.user.name)+'</h1><p>Use Attendance to record people and equipment, then Shift Control to assign crew and locations.</p><div class="pilot-actions">'+(S.boot.user.modules.includes('ATTENDANCE')?'<button class="btn primary" onclick="render(\'ATTENDANCE\')">Open Attendance</button>':'')+(S.boot.user.modules.includes('SHIFT_CONTROL')?'<button class="btn secondary" onclick="render(\'SHIFT_CONTROL\')">Open Shift Control</button>':'')+'</div><p class="note">The server database is the pilot datastore. Use Dashboard for consolidated operational visibility; Google remains the live fallback until final acceptance.</p></div>'+table(['Step','Action'],[['1','Record person IN and equipment opening meters.'],['2','Deploy present, working equipment with eligible crew.'],['3','Release equipment and crew before person OUT or a condition change.'],['4','Save closing meters and check shift closure after shift end.']]));
}
// Keep the source tables, filtering, roster and scroll preservation. Add explicit release and overdue checks.
const originalTables=renderAttendanceTables;
renderAttendanceTables=function(state){
  originalTables(state);
  if(!S.att)return;
  const roster=document.getElementById('roster_setup');if(roster&&!S.boot.user.isManagement)roster.hidden=true;
  const personTable=document.getElementById('person_att_table');
  const equipmentTable=document.getElementById('equipment_att_table');
  if(personTable)personTable.closest('.attendance-card').hidden=!S.att.canPersons;
  if(equipmentTable)equipmentTable.closest('.attendance-card').hidden=!S.att.canEquipment;
  const tableElement=document.getElementById('person_att_table');
  if(tableElement && S.att.canPersons && !document.getElementById('auto_out_button')){
    const b=document.createElement('button');b.id='auto_out_button';b.className='btn secondary small';b.textContent='Check overdue OUT';
    b.onclick=()=>appRun(r=>{toast(r.message);loadAttendance();}).autoCloseAttendance({date:S.att.date,shift:S.att.shift});
    tableElement.before(b);
  }
};
const originalCloseStatus=loadShiftCloseStatus;
loadShiftCloseStatus=function(){
  originalCloseStatus();
  document.querySelectorAll('[id^="scc_"]').forEach(el=>{el.disabled=true;el.title='Change equipment condition in Attendance after releasing assignments.';});
  const intro=document.querySelector('#app .compact-head .note');
  if(intro)intro.textContent='Assign crew and location to PRESENT, WORKING equipment. Change condition in Attendance.';
  const wrap=document.getElementById('sc_body');
  if(wrap){
    const box=document.createElement('div');box.className='panel';
    box.innerHTML='<b>Release crew and deployment</b><p class="note">Release before recording OUT or changing equipment availability.</p><div class="inline"><select id="release_machine" aria-label="Equipment to release">'+opt(S.shiftCtl.equipment,x=>x.id,x=>x.id)+'</select><input id="release_reason" maxlength="250" placeholder="Release reason" aria-label="Release reason"><button class="btn secondary" onclick="releaseMachine()">Release</button></div>';
    wrap.append(box);
  }
};
// Preserve roster scope/search while filtering the reused roster editor.
renderRosterSetupInner=function(){
  const target=document.getElementById('roster_setup_inner');if(!target)return;
  const priorScope=val('roster_assign_scope')||'UNASSIGNED', priorSearch=val('roster_assign_search');
  const r=S.att.roster||{},teams=r.teams||[];
  target.innerHTML='<div class="attendance-tools"><select id="roster_assign_scope" onchange="renderRosterRows()"><option value="UNASSIGNED">Unassigned only</option><option value="ALL">All employees</option></select><input id="roster_assign_search" class="searchbox" placeholder="Search employee" oninput="renderRosterRows()"><span>'+esc(r.assignedCount||0)+' assigned · '+esc(r.unassignedCount||0)+' unassigned</span></div><div id="roster_assign_table"></div><button class="btn primary" onclick="saveRosterAssignments()">Save changed team assignments</button>';
  document.getElementById('roster_assign_scope').value=priorScope;document.getElementById('roster_assign_search').value=priorSearch;renderRosterRows();
};
function renderRosterRows(){
  const teams=S.att.roster.teams||[];
  html('roster_assign_table',table(['Employee','Role','Rotation team'],rosterSetupFiltered().slice(0,250).map(({x,i})=>[
    '<b>'+esc(x.id)+'</b><div class="sub">'+esc(x.name)+'</div>',esc(x.role),
    '<select onchange="setRosterTeam('+i+',this.value)"><option value="">Unassigned</option>'+opt(teams,t=>t.id,t=>t.name+' · this week '+t.currentShift,x.rotationTeam||'')+'</select>'
  ])));
}
function releaseMachine(){appRun(r=>{toast(r.message);loadShiftControl(window.scrollY);}).releaseEquipment({date:S.shiftCtl.date,shift:S.shiftCtl.shift,machineId:val('release_machine'),reason:val('release_reason')});}
function renderUsers(){
  html('app','<div class="panel"><h2>User accounts</h2><p class="note">Assign individual accounts and the modules/shifts each person needs.</p><form id="create_user" class="user-grid"><label>Name<input id="new_name" required maxlength="120"></label><label>User ID<input id="new_id" required maxlength="60" pattern="[A-Za-z0-9_.-]+"></label><label>Initial password<input id="new_password" type="password" required minlength="12" maxlength="128" autocomplete="new-password"></label><button class="btn primary">Create user</button></form></div><div id="user_list" class="panel">Loading…</div>');
  document.getElementById('create_user').onsubmit=event=>{event.preventDefault();appRun(r=>{toast(r.message);document.getElementById('create_user').reset();loadUsers();}).createLoginAccount({loginId:val('new_id'),name:val('new_name'),password:val('new_password')});};loadUsers();
}
function loadUsers(){appRun(users=>{S.users=users;html('user_list','<label>Account<select id="selected_user" onchange="selectUser()"><option value="">Choose account</option>'+users.map((u,i)=>'<option value="'+i+'">'+esc(u.loginId+' — '+u.name)+'</option>').join('')+'</select></label><div id="user_editor"></div>');}).getUserAdminData();}
function selectUser(){
  if(val('selected_user')===''){html('user_editor','');return;}
  const user=S.users[Number(val('selected_user'))];S.selectedUser=user.loginId;
  const checks=[['DASHBOARD','Dashboard'],['PERSON_ATTENDANCE','Person attendance'],['EQUIPMENT_ATTENDANCE','Equipment attendance'],['SHIFT_CONTROL','Shift Control'],['PRODUCTION','Production'],['WB','WB Upload'],['HSD','HSD'],['MASTERS','Masters']].map(([m,label])=>'<label class="access-label"><input type="checkbox" data-module="'+m+'" '+(user.modules.includes(m)?'checked':'')+'>'+label+'</label>').join('');
  const shifts=S.boot.masters.shifts.map(sh=>'<label class="access-label"><input type="checkbox" data-shift="'+esc(sh)+'" '+(user.shifts.includes('ALL')||user.shifts.includes(sh)?'checked':'')+'>'+esc(sh)+'</label>').join('');
  html('user_editor','<div class="user-grid"><div><h3>Modules</h3>'+checks+'</div><div><h3>Shifts</h3>'+shifts+'</div><div><h3>Account</h3><label class="access-label"><input id="user_active" type="checkbox" '+(user.active?'checked':'')+'>Active</label><label class="access-label"><input id="user_admin" type="checkbox" '+(user.admin?'checked':'')+'>Management</label></div></div><button class="btn primary" onclick="saveAccess()">Save access</button><hr><label>New password<input id="reset_password" type="password" minlength="12" maxlength="128" autocomplete="new-password"></label><button class="btn secondary" onclick="resetPassword()">Reset password</button>');
}
function saveAccess(){appRun(r=>{toast(r.message);if(S.selectedUser===S.boot.user.loginId)showLogin(false);else loadUsers();}).saveUserAccess({loginId:S.selectedUser,modules:Array.from(document.querySelectorAll('[data-module]:checked'),x=>x.dataset.module),shifts:Array.from(document.querySelectorAll('[data-shift]:checked'),x=>x.dataset.shift),active:document.getElementById('user_active').checked,admin:document.getElementById('user_admin').checked});}
function resetPassword(){appRun(r=>{toast(r.message);document.getElementById('reset_password').value='';if(S.selectedUser===S.boot.user.loginId)showLogin(false);}).resetAccountPassword({loginId:S.selectedUser,password:val('reset_password')});}

function num(v,d){const n=Number(v||0);return n.toLocaleString('en-IN',{minimumFractionDigits:d||0,maximumFractionDigits:d||0});}
function money(v){return '₹'+Number(v||0).toLocaleString('en-IN',{maximumFractionDigits:0});}
function dashboardKpi(label,value,sub,cls){return '<div class="command-kpi '+(cls||'')+'"><span>'+esc(label)+'</span><b>'+esc(value)+'</b><small>'+esc(sub||'')+'</small></div>';}
function dashboardBars(rows,valueKey,labelKey,unit){if(!rows||!rows.length)return '<div class="emptyviz">No data in this period</div>';const max=Math.max(...rows.map(x=>Number(x[valueKey]||0)),1);return '<div class="barlist">'+rows.map(x=>'<div class="barrow"><span>'+esc(x[labelKey])+'</span><div><i style="width:'+Math.max(2,Number(x[valueKey]||0)/max*100)+'%"></i></div><b>'+esc(num(x[valueKey],valueKey==='tonnes'?1:0))+(unit||'')+'</b></div>').join('')+'</div>';}
function renderDashboard(){
  const today=S.boot.today;
  html('app','<div class="panel command-head"><div><div class="eyebrow">MINE OPERATIONS COMMAND CENTER</div><h2>Management Dashboard</h2><p class="note">Authoritative WB totals + field operations + attendance + equipment + HSD + reconciliation exceptions.</p></div><button class="btn secondary small" onclick="loadDashboard()">Refresh</button></div><div class="panel dash-filters"><button class="period on" data-mode="CURRENT_SHIFT" onclick="dashMode(this,\'CURRENT_SHIFT\')">Current Shift</button><button class="period" data-mode="TODAY" onclick="dashMode(this,\'TODAY\')">Today</button><button class="period" data-mode="7D" onclick="dashMode(this,\'7D\')">7 Days</button><button class="period" data-mode="MTD" onclick="dashMode(this,\'MTD\')">MTD</button><button class="period" data-mode="CUSTOM" onclick="dashMode(this,\'CUSTOM\')">Custom</button><label>From<input id="dash_from" type="date" value="'+esc(today)+'"></label><label>To<input id="dash_to" type="date" value="'+esc(today)+'"></label><label>Shift<select id="dash_shift"><option value="ALL">All shifts</option>'+shiftOptions()+'</select></label><button class="btn primary" onclick="loadDashboard()">Apply</button></div><div id="dashboard_body"><div class="loading">Loading command center…</div></div>');
  S.dashMode='CURRENT_SHIFT'; document.getElementById('dash_shift').value=S.boot.shift; loadDashboard();
}
function dashMode(btn,mode){S.dashMode=mode;document.querySelectorAll('.period').forEach(x=>x.classList.remove('on'));btn.classList.add('on');if(mode==='CURRENT_SHIFT')document.getElementById('dash_shift').value=S.boot.shift;loadDashboard();}
function loadDashboard(){
  const body={mode:S.dashMode||'CURRENT_SHIFT',fromDate:val('dash_from'),toDate:val('dash_to'),shift:val('dash_shift')||'ALL'};
  appRun(function(d){S.dashboard=d;if(S.screen!=='DASHBOARD')return;const k=d.kpis||{};
    const kpis=[dashboardKpi('WB Trips',num(k.wbTrips),'VALID confirmed WB'),dashboardKpi('WB Tonnes',num(k.wbTonnes,1),'Authoritative tonnes','hero'),dashboardKpi('Avg Payload',num(k.avgPayload,2)+' t','per WB trip'),dashboardKpi('Field Trips',num(k.fieldTrips),'recorded production'),dashboardKpi('Matched',num(k.matched),'exact/manual'),dashboardKpi('Match Rate',num(k.matchRate,1)+'%','incl. likely'),dashboardKpi('People Present',num(k.presentPeople),'person-shifts'),dashboardKpi('Working Equipment',num(k.workingEquipment),'equipment-shifts'),dashboardKpi('Deployed',num(k.deployed),'active/events'),dashboardKpi('HSD Issued',num(k.hsdLitres,1)+' L','field issues'),dashboardKpi('Fuel Cost',money(k.hsdCost),'FIFO exact cost'),dashboardKpi('MIS Trips',num(k.misTrips),'submitted driver rows'),dashboardKpi('MIS Operational',num(k.misOperationalQty,1)+' MT','separate from WB'),dashboardKpi('MIS Drafts',num(k.misDrafts),'pending; not counted'),dashboardKpi('MIS WB-linked',num(k.misWbLinkedTrips),'not double-counted'),dashboardKpi('MIS Factor Trips',num(k.misFactorTrips),'estimated by trip factor'),dashboardKpi('OB Trips',num(k.misObTrips),'MIS operational'),dashboardKpi('OB Operational',num(k.misObQty,1)+' MT','separate from WB'),dashboardKpi('ERP Excavation',num(k.shiftExcavationMt,1)+' MT','WB + non-WB trip rules'),dashboardKpi('Processed Ore',num(k.shiftProcessedMt,1)+' MT','WB + exception output'),dashboardKpi('In Transit',num(k.inTransit),'open haulage',k.inTransit?'warn':'')].join('');
    const exc=(d.exceptions||[]).map(x=>'<div class="exception '+esc(x.severity)+'"><span>'+esc(x.label)+'</span><b>'+esc(x.value)+'</b></div>').join('');
    const hourly=dashboardBars((d.hourly||[]).map(x=>({label:x.hour,tonnes:x.tonnes})), 'tonnes','label',' t');
    const materials=dashboardBars(d.materials||[],'tonnes','label',' t');
    const cond=dashboardBars(d.conditions||[],'value','label','');
    const vehicles=table(['Vehicle','Trips','Tonnes','Avg payload'],(d.vehicles||[]).map(x=>[esc(x.vehicle),num(x.trips),num(x.tonnes,2),num(x.avgPayload,2)+' t']));
    const misMaterials=table(['MIS Material','Trips','Operational MT','Avg/trip'],(d.misMaterials||[]).map(x=>[esc(x.label),num(x.trips),num(x.tonnes,2),num(x.avgPayload,2)+' t']));
    const misVehicles=table(['MIS Vehicle','Trips','Operational MT','Avg/trip'],(d.misVehicles||[]).map(x=>[esc(x.vehicle),num(x.trips),num(x.tonnes,2),num(x.avgPayload,2)+' t']));
    const misMachines=table(['Loader / Excavator','Trips','Operational MT','Avg/trip'],(d.misMachines||[]).map(x=>[esc(x.machine),num(x.trips),num(x.tonnes,2),num(x.avgPayload,2)+' t']));
    const loaders=table(['Loader / Excavator','Matched trips','WB tonnes','Avg load'],(d.loaders||[]).map(x=>[esc(x.machine),num(x.trips),num(x.tonnes,2),num(x.avgLoad,2)+' t']));
    const shifts=table(['Date','Shift','WB trips','WB tonnes'],(d.shiftRows||[]).map(x=>[esc(x.date),esc(x.shift),num(x.trips),num(x.tonnes,2)]));
    html('dashboard_body','<div class="dashboard-context"><b>'+esc(d.fromDate)+' → '+esc(d.toDate)+'</b><span>Shift '+esc(d.shift)+'</span><span>WB unmatched '+esc(k.wbUnmatched||0)+'</span><span>Field trips without WB '+esc(k.tripNoWb||0)+'</span><span>Likely '+esc(k.likely||0)+'</span></div><div class="command-kpis">'+kpis+'</div><div class="panel exception-panel"><div class="sectionbar"><b>ACTION REQUIRED</b><span class="sub">Operational exceptions for selected period</span></div><div class="exception-grid">'+exc+'</div></div><div class="command-grid"><div class="panel"><h3>Hourly Haulage Pulse · Tonnes</h3>'+hourly+'</div><div class="panel"><h3>Equipment Condition</h3>'+cond+'</div><div class="panel"><h3>Material Movement · WB Tonnes</h3>'+materials+'</div></div><div class="command-grid two"><div class="panel"><h3>Vehicle Performance</h3>'+vehicles+'</div><div class="panel"><h3>Loader / Excavator Attribution</h3>'+loaders+'</div></div><div class="panel"><div class="sectionbar"><b>MIS MANUAL ENTRY · SUBMITTED REPORTS</b><span class="sub">Operational view; kept separate from authoritative WB totals to prevent double counting.</span></div><div class="command-grid"><div><h3>Material</h3>'+misMaterials+'</div><div><h3>Vehicle</h3>'+misVehicles+'</div><div><h3>Loader / Excavator</h3>'+misMachines+'</div></div></div><div class="panel"><h3>Shift Movement</h3>'+shifts+'</div><div class="dashboard-notes">'+(d.notes||[]).map(x=>'<div>• '+esc(x)+'</div>').join('')+'</div>');
  },function(e){html('dashboard_body','<div class="bad">'+esc(e.message||String(e))+'</div>');}).getDashboard(body);
}


function requestId(prefix){return (prefix||'req')+'-'+(window.crypto&&crypto.randomUUID?crypto.randomUUID():(Date.now()+'-'+Math.random().toString(16).slice(2)));}

/* ---------------- Production ---------------- */
function renderProduction(){html('app','<div class="panel command-head"><div><div class="eyebrow">FIELD PRODUCTION</div><h2>Source → Loading → Hauling → Destination</h2><p class="note">Only PRESENT + WORKING + deployed equipment with PRESENT crew is eligible.</p></div><button class="btn secondary small" onclick="loadProduction()">Refresh</button></div><div id="prod_body"><div class="loading">Loading production desk…</div></div>');loadProduction();}
function loadProduction(){appRun(function(d){S.prod=d;if(S.screen!=='PRODUCTION')return;var activities='<option value="">Activity…</option>'+opt(d.activities||[],x=>x.id,x=>x.id+(x.vehicleRequired?' · vehicle required':'')),locations='<option value="">Select…</option>'+opt(d.locations||[],x=>x.id,x=>x.id+' — '+x.name),products='<option value="">Material…</option>'+opt(d.products||[],x=>x.id,x=>x.id+' — '+x.name),machines='<option value="">Loader / Excavator…</option>'+opt((d.machines||[]).filter(x=>!x.busy),x=>x.id,x=>x.id+' · '+x.locationName+' · '+x.crewId),vehicles='<option value="">Tipper / Dumper…</option>'+opt((d.vehicles||[]).filter(x=>!x.busy),x=>x.id,x=>x.id+(x.vehicleNo?' / '+x.vehicleNo:'')+' · '+x.locationName+' · '+x.crewId);var active=table(['Trip','Status','Loader','Vehicle','Route','Material','Action'],(d.activeTrips||[]).map(x=>['<b>'+esc(x.seq||'—')+'</b><div class="sub">'+esc(x.tripId.slice(0,8))+'</div>',tag(x.status),esc(x.machine),esc(x.vehicle||'—'),esc(x.source+' → '+(x.destination||'—')),esc(x.material||'—'),x.status==='LOADING'?'<button class="btn primary small" data-trip="'+esc(x.tripId)+'" onclick="prodLoaded(this.dataset.trip)">LOADED / RELEASE</button>':'<button class="btn secondary small" data-trip="'+esc(x.tripId)+'" onclick="prodUnloaded(this.dataset.trip)">UNLOADED / READY</button>']));var recent=table(['Seq','Vehicle','Loader','Source → Destination','Material','Start','Loaded','Unload','Status'],(d.recent||[]).map(x=>[esc(x.seq||'—'),esc(x.vehicle||'—'),esc(x.machine),esc(x.source+' → '+(x.destination||'—')),esc(x.material||'—'),esc(x.start),esc(x.loaded),esc(x.unloaded),tag(x.status)]));html('prod_body','<div class="panel"><div class="sectionbar"><div><b>NEW LOADING EVENT</b><div class="sub">'+esc(d.date)+' · Shift '+esc(d.shift)+' · server '+esc(d.time)+'</div></div></div><div class="ops-form grid3"><label>Source location<select id="prod_source">'+locations+'</select></label><label>Destination<select id="prod_dest">'+locations+'</select></label><label>Activity<select id="prod_activity">'+activities+'</select></label><label>Loader / Excavator<select id="prod_machine">'+machines+'</select></label><label>Tipper / Dumper<select id="prod_vehicle">'+vehicles+'</select></label><label>Material<select id="prod_material">'+products+'</select></label></div><button class="btn primary" onclick="startProduction()">START LOADING</button></div><div class="panel"><h3>Live Trips</h3>'+active+'</div><div class="panel"><h3>Recent Production</h3>'+recent+'</div>');}).getProductionDesk();}
function startProduction(){appRun(function(r){toast(r.message);loadProduction();}).startProductionTrip({requestId:requestId('trip'),sourceLocationId:val('prod_source'),destinationLocationId:val('prod_dest'),activity:val('prod_activity'),machineId:val('prod_machine'),vehicleId:val('prod_vehicle'),materialId:val('prod_material')});}
function prodLoaded(id){appRun(function(r){toast(r.message);loadProduction();}).markTripLoaded({tripId:id});}
function prodUnloaded(id){appRun(function(r){toast(r.message);loadProduction();}).markTripUnloaded({tripId:id});}

/* ---------------- Weighbridge ---------------- */
function renderWb(){html('app','<div class="panel command-head"><div><div class="eyebrow">WEIGHBRIDGE</div><h2>Shift-wise WB Upload & Reconciliation</h2><p class="note">VALID confirmed WB rows are authoritative for site trips/tonnes even when field matching is pending.</p></div><button class="btn secondary small" onclick="loadWb();loadWbMonitor()">Refresh</button></div><div id="wb_monitor"><div class="panel"><div class="loading">Loading WB coverage…</div></div></div><div class="panel wb-upload"><div class="grid3"><label>Operating date<input id="wb_date" type="date" value="'+esc(S.boot.today)+'"></label><label>Shift<select id="wb_shift">'+shiftOptions()+'</select></label><label>XLSX file<input id="wb_file" type="file" accept=".xlsx"></label></div><div class="btnrow"><button class="btn primary" onclick="uploadWb()">UPLOAD / PREVIEW</button><button class="btn secondary" onclick="loadWb()">LOAD STATUS</button></div></div><div id="wb_body"><div class="loading">Loading WB status…</div></div>');document.getElementById('wb_shift').value=S.boot.shift;loadWbMonitor();loadWb();var q=document.createElement('div');q.id='wb_history_queue';document.getElementById('app').appendChild(q);loadWbHistoryQueue();}
// NMTPL_WB_MONITOR_DASHBOARD_V1
function wbCovTag(status){
  var s=String(status||'').toUpperCase(),c=s==='UPDATED'?'ok':(s==='REVIEW'||s==='MISSING'?'bad':'warn');
  return '<span class="tag '+c+' wb-cov-tag">'+esc(status||'—')+'</span>';
}
function loadWbMonitor(){
  appRun(function(d){
    if(S.screen!=='WB')return;
    var g=d.gmail||{},c=d.counts||{},last=d.lastWb||null;
    var gmailState=String(g.state||'UNKNOWN').toUpperCase();
    var gmailClass=gmailState==='RUNNING'?'ok':(gmailState==='ERROR'||gmailState==='STALE'?'bad':'warn');
    var cards='<div class="wb-monitor-kpis">'
      +'<div class="wb-monitor-card"><span>Gmail Parser</span><b><span class="tag '+gmailClass+'">'+esc(gmailState)+'</span></b><small>'+esc(g.lastCheck||'No poll recorded')+'</small></div>'
      +'<div class="wb-monitor-card"><span>Last WB Updated</span><b>'+esc(last?(last.date+' · '+last.shift):'—')+'</b><small>'+esc(last?last.fileName:'No confirmed batch')+'</small></div>'
      +'<div class="wb-monitor-card"><span>Updated</span><b>'+esc(c.UPDATED||0)+'</b><small>confirmed shifts</small></div>'
      +'<div class="wb-monitor-card"><span>Pending</span><b>'+esc(c.PENDING||0)+'</b><small>waiting / unconfirmed</small></div>'
      +'<div class="wb-monitor-card"><span>Needs Attention</span><b>'+esc((Number(c.REVIEW||0)+Number(c.MISSING||0)))+'</b><small>'+esc(c.REVIEW||0)+' review · '+esc(c.MISSING||0)+' missing</small></div>'
      +'</div>';

    var shifts=d.shifts||[];
    var rows=(d.coverage||[]).map(function(r){
      var cells=[esc(r.date)];
      shifts.forEach(function(sh){
        var x=(r.shifts||{})[sh]||{},title=(x.fileName?x.fileName+' · ':'')+(x.valid||0)+' valid / '+(x.review||0)+' review';
        cells.push('<span title="'+esc(title)+'">'+wbCovTag(x.status)+'</span>');
      });
      return cells;
    });
    var coverage=table(['Operating Date'].concat(shifts.map(function(s){return 'Shift '+s;})),rows);
    var note='<div class="wb-monitor-note">Pending = shift ended but still within the 1-hour receipt window, or a clean PREVIEW is awaiting confirmation. Missing = 1-hour window passed with no confirmed WB batch.</div>';
    html('wb_monitor','<div class="panel wb-monitor-panel"><div class="sectionbar"><div><h3>WB Coverage & Gmail Monitor</h3><div class="sub">Last '+esc(d.days)+' operating days · SQL confirmation is the final UPDATED status.</div></div></div>'+cards+note+coverage+'</div>');
  },function(e){
    html('wb_monitor','<div class="panel"><div class="bad">WB monitor: '+esc(e.message)+'</div></div>');
  }).getWbMonitor({days:14});
}
function loadWb(){appRun(function(d){S.wb=d;if(S.screen!=='WB')return;var sel=d.selected,periodNote='<div class="sub wb-selected-period">Requested: '+esc(d.requestedDate||val('wb_date'))+' / Shift '+esc(d.requestedShift||val('wb_shift'))+'</div>',summary=sel?'<div class="wb-summary"><div><span>File</span><b>'+esc(sel.fileName)+'</b></div><div><span>Status</span><b>'+tag(sel.status)+'</b></div><div><span>VALID</span><b>'+esc(sel.valid)+'</b></div><div><span>REVIEW</span><b>'+esc(sel.review)+'</b></div></div>':'<div class="note">No WB batch for this date/shift.</div>';var confirm=sel&&sel.status==='PREVIEW'&&Number(sel.valid)>0?'<button class="btn primary" data-batch="'+esc(sel.batchId)+'" onclick="confirmWb(this.dataset.batch)">CONFIRM WB BATCH</button>':'';var rows=table(['Status','Vehicle','Time','Material','Source','Destination','Net t','Issue'],(d.rows||[]).slice(0,500).map(x=>[tag(x.status),esc(x.vehicle),esc(x.time),esc(x.material),esc(x.source),esc(x.destination),Number(x.tonnes||0).toFixed(2),esc(x.issue||'')]));html('wb_body','<div class="panel">'+periodNote+summary+'<div class="btnrow">'+confirm+'</div></div><div class="panel"><h3>Preview / Confirmed Rows</h3>'+rows+'</div>');},function(e){html('wb_body','<div class="bad">'+esc(e.message)+'</div>');}).getWbDesk(val('wb_date'),val('wb_shift'));}
async function uploadWb(){var f=document.getElementById('wb_file').files[0];if(!f){toast('Choose the WB XLSX file.',true);return;}var fd=new FormData();fd.append('operatingDate',val('wb_date'));fd.append('shift',val('wb_shift'));fd.append('file',f);try{var d=await NMTPLNet.json('/api/web/wb-upload',{method:'POST',body:fd,timeoutMs:60000});toast(d.message);loadWb();}catch(e){toast(e.message,true);}}
function confirmWb(id){appRun(function(r){toast(r.message);loadWb();}).confirmWbBatch({batchId:id});}

// NMTPL_WB_CONTROL_CENTER_V1
function openHistoricalWb(day,shift){
  var d=document.getElementById('wb_date'),s=document.getElementById('wb_shift');
  if(d)d.value=day;if(s)s.value=shift;
  loadWb();
  var el=document.getElementById('wb_body');
  if(el)el.scrollIntoView({behavior:'smooth',block:'start'});
}
function wbHistoryTag(status){
  var x=String(status||'').toUpperCase();
  var c=(x.indexOf('CONFIRMED')===0)?'ok':((x==='MISSING'||x==='REVIEW')?'bad':'warn');
  return '<span class="tag '+c+'">'+esc(status||'—')+'</span>';
}
function loadWbHistoryQueue(){
  appRun(function(d){
    if(S.screen!=='WB')return;
    var rows=(d.rows||[]).map(function(x){
      var action='<button class="btn secondary small" data-day="'+esc(x.date)+'" data-shift="'+esc(x.shift)+'" onclick="openHistoricalWb(this.dataset.day,this.dataset.shift)">OPEN</button>';
      return [esc(x.date),esc(x.shift),wbHistoryTag(x.status),esc(x.file||'—'),action];
    });
    var c=d.counts||{};
    var summary='<div class="wb-history-summary">'
      +'<span>Review <b>'+esc(c.REVIEW||0)+'</b></span>'
      +'<span>Timeout <b>'+esc(c.TIMEOUT||0)+'</b></span>'
      +'<span>Missing <b>'+esc(c.MISSING||0)+'</b></span>'
      +'<span>Available <b>'+esc(c.AVAILABLE||0)+'</b></span>'
      +'</div>';
    html('wb_history_queue','<div class="panel"><div class="sectionbar"><div><h3>Historical WB Queue</h3><div class="sub">'+esc(d.source||'No backfill report')+' · read-only audit view</div></div><button class="btn secondary small" onclick="loadWbHistoryQueue()">Refresh</button></div>'+summary+table(['Date','Shift','Status','File','Action'],rows)+'</div>');
  },function(e){
    html('wb_history_queue','<div class="panel"><div class="bad">Historical WB queue: '+esc(e.message)+'</div></div>');
  }).getWbHistoryQueue({});
}

/* ---------------- HSD ---------------- */
function renderHsd(){html('app','<div class="panel command-head"><div><div class="eyebrow">HSD CONTROL</div><h2>Petrol Pump → Tanker → Vehicle / Machine</h2><p class="note">Fuel issues consume exact purchase lots FIFO. No weighted-average tanker rate.</p></div><button class="btn secondary small" onclick="loadHsd()">Refresh</button></div><div id="hsd_body"><div class="loading">Loading HSD desk…</div></div>');loadHsd();}
function loadHsd(){appRun(function(d){S.hsd=d;if(S.screen!=='HSD')return;var tanker='<option value="">Select tanker…</option>'+opt(d.tankers||[],x=>x.id,x=>x.id+(x.vehicleNo?' / '+x.vehicleNo:'')+' · '+Number(x.stock).toFixed(1)+' L'),machine='<option value="">Select machine…</option>'+opt(d.machines||[],x=>x.id,x=>x.id+' · '+x.group+' · '+(x.locationName||'No location'));var receipts=table(['Time','Tanker','Supplier','Invoice','Received L','Remaining L','₹/L','Value'],(d.receipts||[]).map(x=>[esc(x.time),esc(x.tanker),esc(x.supplier),esc(x.invoice),num(x.litres,1),num(x.remaining,1),num(x.rate,2),money(x.amount)]));var issues=table(['Time','Tanker','Machine','Litres','FIFO cost','Location','Meter','Reference'],(d.issues||[]).map(x=>[esc(x.time),esc(x.tanker),esc(x.machine),num(x.litres,1),money(x.amount),esc(x.location),esc((x.meterType||'')+(x.meter!=null?' '+x.meter:'')),esc(x.reference)]));html('hsd_body','<div class="grid2"><div class="panel"><h3>1. PETROL PUMP / SUPPLIER → TANKER</h3><div class="ops-form"><label>Receiving tanker<select id="hr_tanker">'+tanker+'</select></label><label>Litres<input id="hr_litres" type="number" min="0" step="0.01"></label><label>Rate ₹/L<input id="hr_rate" type="number" min="0" step="0.0001"></label><label>Supplier / Petrol Pump<input id="hr_supplier"></label><label>Invoice / Challan<input id="hr_invoice"></label><label>Pump location<input id="hr_pump"></label></div><button class="btn primary" onclick="saveHsdReceiptUi()">RECEIVE FUEL</button></div><div class="panel"><h3>2. TANKER → VEHICLE / MACHINE</h3><div class="ops-form"><label>Supplying tanker<select id="hi_tanker">'+tanker+'</select></label><label>Receiving machine<select id="hi_machine">'+machine+'</select></label><label>Litres<input id="hi_litres" type="number" min="0" step="0.01"></label><label>HMR/KMR reading<input id="hi_meter" type="number" step="0.01"></label><label>Voucher / Reference<input id="hi_ref"></label></div><button class="btn primary" onclick="saveHsdIssueUi()">SAVE HSD ISSUE</button></div></div><div class="panel"><h3>Recent Tanker Receipts</h3>'+receipts+'</div><div class="panel"><h3>Recent Machine Issues</h3>'+issues+'</div>');}).getHsdDesk();}
function saveHsdReceiptUi(){appRun(function(r){toast(r.message);loadHsd();}).saveHsdReceipt({requestId:requestId('hsdr'),tankerId:val('hr_tanker'),litres:val('hr_litres'),ratePerL:val('hr_rate'),supplier:val('hr_supplier'),invoiceNo:val('hr_invoice'),pumpLocation:val('hr_pump')});}
function saveHsdIssueUi(){appRun(function(r){toast(r.message+' Cost '+money(r.amount));loadHsd();}).saveHsdIssue({requestId:requestId('hsdi'),tankerId:val('hi_tanker'),machineId:val('hi_machine'),litres:val('hi_litres'),meterReading:val('hi_meter'),reference:val('hi_ref')});}

/* ---------------- Masters ---------------- */
function renderMasters(){html('app','<div class="panel command-head"><div><div class="eyebrow">MASTER DATA</div><h2>Operations Masters</h2><p class="note">Create/update records; make old records inactive instead of deleting history.</p></div><button class="btn secondary small" onclick="loadMasters()">Refresh</button></div><div class="panel"><label>Master<select id="master_type" onchange="renderMasterTable()"><option value="PERSON">People</option><option value="EQUIPMENT">Equipment</option><option value="LOCATION">Locations</option><option value="PRODUCT">Products</option><option value="ACTIVITY">Activities</option><option value="TANKER">HSD Tankers</option></select></label></div><div id="master_body"><div class="loading">Loading masters…</div></div>');loadMasters();}
function loadMasters(){appRun(function(d){S.mastersDesk=d;renderMasterTable();}).getMastersDesk();}
function renderMasterTable(){if(!S.mastersDesk)return;var t=val('master_type')||'PERSON',cfg={PERSON:['persons',['id','name','role','department','rotationTeam','active']],EQUIPMENT:['equipment',['id','vehicleNo','type','group','ownership','active']],LOCATION:['locations',['id','name','type','active']],PRODUCT:['products',['id','name','active']],ACTIVITY:['activities',['id','vehicleRequired','active']],TANKER:['tankers',['id','vehicleNo','capacity','active']]}[t],rows=S.mastersDesk[cfg[0]]||[],fields=cfg[1];var form='<div class="master-form">'+fields.map(f=>'<label>'+esc(f)+(f==='active'||f==='vehicleRequired'?'<select id="mf_'+f+'"><option value="true">Yes</option><option value="false">No</option></select>':'<input id="mf_'+f+'">')+'</label>').join('')+'</div><button class="btn primary" onclick="saveMasterUi()">SAVE MASTER</button>';var tbl=table(fields.map(x=>x),rows.slice(0,500).map(r=>fields.map(f=>esc(String(r[f]==null?'':r[f])))));html('master_body','<div class="panel"><h3>New / Update '+esc(t)+'</h3>'+form+'</div><div class="panel"><h3>'+esc(t)+' Records</h3>'+tbl+'</div>');}
function saveMasterUi(){var t=val('master_type'),cfg={PERSON:['id','name','role','department','rotationTeam','active'],EQUIPMENT:['id','vehicleNo','type','group','ownership','active'],LOCATION:['id','name','type','active'],PRODUCT:['id','name','active'],ACTIVITY:['id','vehicleRequired','active'],TANKER:['id','vehicleNo','capacity','active']}[t],row={};cfg.forEach(f=>{var v=val('mf_'+f);row[f]=(f==='active'||f==='vehicleRequired')?v==='true':v;});appRun(function(r){toast(r.message);loadMasters();}).saveMasterRecord({table:t,row:row});}

window.addEventListener('load',async()=>{try{const status=await request('setup-status');if(status.setupRequired)showLogin(true);else {try{await enterApp();}catch{showLogin(false);}}}catch(e){html('app','<div class="panel"><h2>Server unavailable</h2><p>'+esc(e.message)+'</p><button class="btn primary" onclick="location.reload()">Retry</button></div>');}});

/* NMTPL_SIMPLE_UI_V4_START */
(function(){
  function addDayV4_(iso,delta){
    var p=String(iso||'').split('-').map(Number);if(p.length!==3||!p[0]||!p[1]||!p[2])return iso;
    return new Date(Date.UTC(p[0],p[1]-1,p[2]+delta)).toISOString().slice(0,10);
  }
  function previousShiftV4_(d,s){
    s=String(s||'').toUpperCase();
    if(s==='B')return{date:d,shift:'A'};
    if(s==='C')return{date:d,shift:'B'};
    if(s==='A')return{date:addDayV4_(d,-1),shift:'C'};
    return{date:d,shift:s};
  }
  function liveShiftV4_(){return S.attLiveV4||{date:(S.boot&&S.boot.today)||'',shift:(S.boot&&S.boot.shift)||''};}
  function selectedAttV4_(){return{date:val('att_date')||(S.att&&S.att.date)||'',shift:val('att_shift')||(S.att&&S.att.shift)||''};}
  function sameV4_(a,b){return a&&b&&String(a.date)===String(b.date)&&String(a.shift)===String(b.shift);}

  function updateAttQuickV4_(){
    if(S.screen!=='ATTENDANCE')return;
    var live=liveShiftV4_(),prev=previousShiftV4_(live.date,live.shift),sel=selectedAttV4_();
    var c=document.getElementById('att_v4_current'),p=document.getElementById('att_v4_previous');
    if(c){c.textContent='Current '+live.shift;c.classList.toggle('active',sameV4_(sel,live));c.title=live.date+' · Shift '+live.shift;}
    if(p){p.textContent='Previous '+prev.shift;p.classList.toggle('active',sameV4_(sel,prev));p.title=prev.date+' · Shift '+prev.shift;}
  }
  window.attQuickV4_=function(which){
    var live=liveShiftV4_(),ctx=which==='PREVIOUS'?previousShiftV4_(live.date,live.shift):live;
    var d=document.getElementById('att_date'),s=document.getElementById('att_shift');if(!d||!s)return;
    d.value=ctx.date;s.value=ctx.shift;loadAttendance();
  };

  function tabBtnV4_(id,label){return '<button type="button" id="att_v4_'+id.toLowerCase()+'" class="att-v4-tab" onclick="attTabV4_(\''+id+'\')">'+esc(label)+'</button>';}
  function renderAttTabsV4_(){
    var box=document.getElementById('att_v4_tabs');if(!box||!S.att)return;
    var h='';if(S.att.canPersons!==false)h+=tabBtnV4_('PEOPLE','Employee Attendance');
    if(S.att.canEquipment!==false)h+=tabBtnV4_('EQUIPMENT','Equipment Attendance');
    if(S.boot&&S.boot.user&&S.boot.user.isManagement)h+=tabBtnV4_('ROSTER','Shift Roster');
    box.innerHTML=h;
    if(!S.attTabV4)S.attTabV4=S.att.canPersons!==false?'PEOPLE':'EQUIPMENT';
  }
  function showV4_(el,on){if(el){el.hidden=!on;el.style.display=on?'':'none';}}
  function applyAttTabV4_(){
    if(S.screen!=='ATTENDANCE'||!S.att)return;renderAttTabsV4_();
    var mode=S.attTabV4||'PEOPLE',pt=document.getElementById('person_att_table'),et=document.getElementById('equipment_att_table');
    var pc=pt&&pt.closest('.attendance-card'),ec=et&&et.closest('.attendance-card'),roster=document.getElementById('roster_setup');
    if(pc){showV4_(pc,mode!=='EQUIPMENT'&&S.att.canPersons!==false);showV4_(pc.querySelector('.sectionbar'),mode==='PEOPLE');showV4_(pc.querySelector('.attendance-tools'),mode==='PEOPLE');showV4_(pt,mode==='PEOPLE');showV4_(pc.querySelector('.btnrow'),mode==='PEOPLE');var ab=document.getElementById('auto_out_button');if(ab)showV4_(ab,mode==='PEOPLE');}
    if(ec)showV4_(ec,mode==='EQUIPMENT'&&S.att.canEquipment!==false);
    if(roster)showV4_(roster,mode==='ROSTER'&&!!(S.boot&&S.boot.user&&S.boot.user.isManagement));
    ['PEOPLE','EQUIPMENT','ROSTER'].forEach(function(id){var b=document.getElementById('att_v4_'+id.toLowerCase());if(b)b.classList.toggle('active',mode===id);});
  }
  window.attTabV4_=function(mode){S.attTabV4=mode;applyAttTabV4_();};

  function ensureAttActionFilterV4_(){
    var p=document.getElementById('person_scope');
    if(p&&!p.querySelector('option[value="ACTION"]'))p.insertAdjacentHTML('afterbegin','<option value="ACTION">Action required</option><option value="PRESENT">Present only</option>');
    var e=document.getElementById('equipment_filter');
    if(e&&!document.getElementById('equipment_scope')){var s=document.createElement('select');s.id='equipment_scope';s.setAttribute('onchange','renderAttendanceTables()');s.innerHTML='<option value="ALL">All equipment</option><option value="ACTION">Closing meter pending</option><option value="PRESENT">Present only</option><option value="MARKED">Marked this shift</option>';e.parentNode.insertBefore(s,e);}
  }

  var baseFilteredPersonsV4=filteredPersons;
  filteredPersons=function(){
    var scope=val('person_scope')||'ROSTER';
    if(scope!=='ACTION'&&scope!=='PRESENT')return baseFilteredPersonsV4();
    var f=val('person_filter')||'ALL',q=String(val('person_search')||'').toUpperCase();
    return(S.att.persons||[]).map(function(x,i){return{x:x,i:i};}).filter(function(o){var x=o.x,b=roleBucket(x.role),txt=(x.id+' '+x.name+' '+x.role+' '+(x.rotationTeam||'')).toUpperCase();var ok=scope==='PRESENT'?x.attendance==='PRESENT':((x.attendance==='PRESENT'&&!x.outTime)||x.reviewStatus==='REVIEW');return ok&&(f==='ALL'||b===f)&&(!q||txt.indexOf(q)>=0);});
  };
  var baseFilteredEquipmentV4=filteredEquipment;
  filteredEquipment=function(){
    var scope=val('equipment_scope')||'ALL';if(scope==='ALL')return baseFilteredEquipmentV4();
    var f=val('equipment_filter')||'ALL',q=String(val('equipment_search')||'').toUpperCase();
    return(S.att.equipment||[]).map(function(x,i){return{x:x,i:i};}).filter(function(o){var x=o.x,txt=(x.id+' '+x.type+' '+x.group).toUpperCase();var ok=scope==='MARKED'?!!x.attendance:scope==='PRESENT'?x.attendance==='PRESENT':(x.attendance==='PRESENT'&&(x.closing===''||x.closing==null));return ok&&(f==='ALL'||x.group===f)&&(!q||txt.indexOf(q)>=0);});
  };

  var baseRenderAttendanceTablesV4=renderAttendanceTables;
  renderAttendanceTables=function(state){var out=baseRenderAttendanceTablesV4(state);ensureAttActionFilterV4_();applyAttTabV4_();updateAttQuickV4_();return out;};

  renderAttendance=function(){
    var d=S.boot.today,s=S.boot.shift;
    html('app','<div class="panel att-v4-head"><div class="att-v4-line"><h2>Attendance</h2><div class="att-v4-quick"><button id="att_v4_current" class="att-v4-context" onclick="attQuickV4_(\'CURRENT\')">Current</button><button id="att_v4_previous" class="att-v4-context" onclick="attQuickV4_(\'PREVIOUS\')">Previous</button></div><div class="att-v4-inputs"><input id="att_date" type="date" value="'+esc(d)+'"><select id="att_shift">'+shiftOptions()+'</select><button class="btn primary" onclick="loadAttendance()">Load</button></div></div><div id="att_v4_tabs" class="att-v4-tabs"></div></div><div id="att_body"><div class="loading">Loading…</div></div>');
    document.getElementById('att_shift').value=s;
    appRun(function(ctx){S.attLiveV4=ctx;updateAttQuickV4_();},function(){updateAttQuickV4_();}).getLiveContext();
    loadAttendance();
  };

  // ----- WB: keep only the working SQL view. Remove duplicate monitor/history panels. -----
  function wbCardV4_(label,value,sub,cls){return '<div class="wb-v4-card '+(cls||'')+'"><span>'+esc(label)+'</span><b>'+esc(String(value))+'</b><small>'+esc(sub||'')+'</small></div>';}
  function cleanWbV4_(){
    if(S.screen!=='WB')return;
    ['wb_monitor','wb_history_v3'].forEach(function(id){var e=document.getElementById(id);if(e)e.remove();});
    document.querySelectorAll('#app .bad').forEach(function(el){var t=String(el.textContent||'').trim();if(/^WB monitor:/i.test(t)||/^Historical WB queue:/i.test(t)){var p=el.closest('.panel');if(p)p.remove();else el.remove();}});
  }
  window.loadWbMonitor=function(){cleanWbV4_();};

  renderWb=function(){
    html('app','<div class="panel wb-v4-head"><div><div class="eyebrow">WEIGHBRIDGE</div><h2>WB Upload & SQL Status</h2></div><button class="btn secondary small" onclick="loadWb()">Refresh</button></div><div class="panel wb-upload"><div class="grid3"><label>Operating date<input id="wb_date" type="date" value="'+esc(S.boot.today)+'"></label><label>Shift<select id="wb_shift">'+shiftOptions()+'</select></label><label>XLSX file<input id="wb_file" type="file" accept=".xlsx"></label></div><div class="btnrow"><button class="btn primary" onclick="uploadWb()">UPLOAD / PREVIEW</button><button class="btn secondary" onclick="loadWb()">LOAD STATUS</button></div></div><div id="wb_body"><div class="loading">Loading WB status…</div></div>');
    document.getElementById('wb_shift').value=S.boot.shift;loadWb();
    if(S.wbV4Obs)try{S.wbV4Obs.disconnect();}catch(_){}
    S.wbV4Obs=new MutationObserver(cleanWbV4_);S.wbV4Obs.observe(document.getElementById('app'),{childList:true,subtree:true});
  };

  loadWb=function(){
    appRun(function(d){
      S.wb=d;if(S.screen!=='WB')return;cleanWbV4_();
      var sel=d.selected,all=d.rows||[],valid=all.filter(function(x){return x.status==='VALID';}),review=all.filter(function(x){return x.status==='REVIEW';});
      var mapped=valid.filter(function(x){return !!x.vehicleId;}).length,unmapped=valid.length-mapped,tonnes=valid.reduce(function(a,x){return a+Number(x.tonnes||0);},0);
      var state=sel?(sel.status==='CONFIRMED'?'UPDATED':'PREVIEW'):'NO DATA';
      var snap='<div class="panel wb-v4-snapshot"><div class="sectionbar"><b>SQL UPDATE SNAPSHOT</b><span class="tag '+(state==='UPDATED'?'ok':state==='PREVIEW'?'warn':'')+'">'+esc(state)+'</span></div><div class="wb-v4-grid">'
       +wbCardV4_('DB Rows',all.length,'VALID + REVIEW')+wbCardV4_('Valid Rows',valid.length,'eligible movements','ok')+wbCardV4_('WB Tonnes',tonnes.toFixed(2),'VALID net tonnes')+wbCardV4_('Vehicle Mapped',mapped,'equipment master','ok')+wbCardV4_('Unmapped',unmapped,'needs master/alias',unmapped?'warn':'')+wbCardV4_('Review',review.length,'data exceptions',review.length?'warn':'')+'</div></div>';
      var summary=sel?'<div class="panel wb-v4-batch"><b>'+esc(sel.fileName)+'</b><span>'+tag(sel.status)+'</span><span>VALID '+esc(sel.valid)+'</span><span>REVIEW '+esc(sel.review)+'</span>'+(sel.status==='PREVIEW'&&Number(sel.valid)>0?'<button class="btn primary small" data-batch="'+esc(sel.batchId)+'" onclick="confirmWb(this.dataset.batch)">CONFIRM</button>':'')+'</div>':'<div class="panel note">No WB batch for this date/shift.</div>';
      var rowsHtml=table(['Status','Vehicle','Time','Material','Source','Destination','Net t','Issue'],all.slice(0,500).map(function(x){return[tag(x.status),esc(x.vehicle),esc(x.time),esc(x.material),esc(x.source),esc(x.destination),Number(x.tonnes||0).toFixed(2),esc(x.issue||'')];}));
      html('wb_body',snap+summary+'<div class="panel"><h3>Preview / Confirmed Rows</h3>'+rowsHtml+'</div>');cleanWbV4_();
    },function(e){html('wb_body','<div class="bad">'+esc(e.message)+'</div>');}).getWbDesk(val('wb_date'),val('wb_shift'));
  };
})();
/* NMTPL_SIMPLE_UI_V4_END */
