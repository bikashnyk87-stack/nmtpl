/* KOCP unloading-point MCL factors, approved rule calculation and reporting.
   All values are loaded from the existing KOCP masters, never hardcoded. */
const koPointState={routes:[],materials:{COAL:[],OB:[]},rules:[]};
const koPointKinds={COAL:"COAL_AVG_MT_PER_TRIP",OB:"OB_CUM_PER_TRIP"};
const koUnit=k=>k==="OB"?"CUM/TRIP":"MT/TRIP";

function koPointOpts(rows,id,text,placeholder){
  return '<option value="">'+esc(placeholder)+'</option>'+rows.map(r=>
    '<option value="'+esc(r[id])+'">'+esc(r[text])+'</option>').join('');
}
function koPointMaterials(kind){
  return (koPointState.materials[kind]||[]).filter(r=>r.active&&r.materialId);
}
function koPointDestinations(kind){
  const unique=new Map();
  for(const r of koPointState.routes.filter(x=>x.kind===kind&&x.active&&x.destinationLocationId)){
    if(!unique.has(r.destinationLocationId))unique.set(r.destinationLocationId,{
      id:r.destinationLocationId,name:r.destination
    });
  }
  return [...unique.values()].sort((a,b)=>a.name.localeCompare(b.name));
}
function koPointChangeKind(){
  const kind=$('pfKind').value;
  const d=$('pfDest'),m=$('pfMaterial');
  d.innerHTML=koPointOpts(koPointDestinations(kind),'id','name','Choose unloading point');
  m.innerHTML=koPointOpts(koPointMaterials(kind),'materialId','name','Choose material');
  $('pfUnit').textContent=koUnit(kind);
  koPointChangeDestination();
}
function koPointChangeDestination(){
  const kind=$('pfKind').value,dest=$('pfDest').value;
  const list=koPointState.routes.filter(r=>r.active&&r.kind===kind&&r.destinationLocationId===dest);
  const route=$('pfRoute');
  route.innerHTML=koPointOpts(list.map(r=>({
    routeId:r.routeId,
    description:r.group+' · '+r.category+' · '+r.distanceRange
  })),'routeId','description','All routes at this unloading point');
}
function koPointChangeRoute(){
  const r=koPointState.routes.find(x=>x.routeId===$('pfRoute').value);
  if(!r)return;
  const name=(r.group+' '+r.category).toUpperCase();
  let code;
  if(r.kind==='COAL')code=name.includes('REJECT')?'REJECT':'COAL';
  else if(name.includes('RE-HAND')||name.includes('REHAND'))code='REHANDLING_OB';
  else if(name.includes('SOFT'))code='SOFT_OB';
  else if(name.includes('HARD'))code='HARD_OB';
  const material=koPointMaterials(r.kind).find(x=>x.typeCode===code);
  if(material)$('pfMaterial').value=material.materialId;
}
function koPointName(id,list,key,label){
  const found=list.find(x=>x[key]===id);return found?found[label]:id||'—';
}
async function renderKocpPointFactors(){
  const [rules,routes,catalog]=await Promise.all([
    api('/api/sites/KOCP/weight-factors'),
    api('/api/sites/KOCP/routes'),
    api('/api/sites/KOCP/material-types')
  ]);
  koPointState.rules=rules;koPointState.routes=routes;
  koPointState.materials=catalog;
  const date=state.ctx.operatingDate;
  const form=`<p class="simple-note">Set a separate approved average for each unloading point. Choose a route/distance only if its average differs from other routes to the same point. No mine-wide default is used.</p>
    <div class="form-grid">
      <div class="field"><span>Material type</span><select id="pfKind" onchange="koPointChangeKind()">
        <option value="COAL">Coal / Reject (MT)</option><option value="OB">OB (CuM)</option></select></div>
      <div class="field"><span>Unloading point *</span><select id="pfDest" onchange="koPointChangeDestination()"></select></div>
      <div class="field"><span>Route / distance (optional)</span><select id="pfRoute" onchange="koPointChangeRoute()"></select></div>
      <div class="field"><span>Material *</span><select id="pfMaterial"></select></div>
      <div class="field"><span>Approved average / trip *</span><input id="pfValue" type="number" step="0.000001" min="0.000001" placeholder="Enter MCL-approved value"></div>
      <div class="field"><span>Unit</span><strong id="pfUnit">MT/TRIP</strong></div>
      <div class="field"><span>Effective from *</span><input id="pfFrom" type="date" value="${date}"></div>
      <div class="field"><span>Effective to (optional)</span><input id="pfTo" type="date"></div>
      <div class="field"><span>Operating date (optional)</span><input id="pfOpDate" type="date"></div>
      <div class="field"><span>Shift</span><select id="pfShift">
        <option value="">All shifts</option>${state.ctx.shifts.map(s=>'<option value="'+esc(s.shift)+'">'+esc(s.shift)+'</option>').join('')}</select></div>
      <div class="field"><span>Vehicle class (optional, exact type/group)</span><input id="pfClass" placeholder="Blank = all classes"></div>
      <div class="field"><span>MCL reference no. *</span><input id="pfRef" maxlength="120" placeholder="Approved sheet / circular reference"></div>
      <div class="form-actions"><button class="btn primary" onclick="koPointSaveRule()">Create Draft</button></div>
    </div>`;
  const dests=[...koPointDestinations('COAL'),...koPointDestinations('OB')];
  const items=rules.map(r=>{
    const kind=r.factorType==='OB_CUM_PER_TRIP'?'OB':'COAL';
    const route=koPointState.routes.find(x=>x.routeId===r.routeId);
    const material=koPointMaterials(kind).find(x=>x.materialId===r.materialId);
    const dest=dests.find(x=>x.id===r.destinationLocationId);
    return `<tr><td>${esc(kind)}</td><td>${esc(material?.name||r.materialId||'—')}</td>
      <td>${esc(dest?.name||r.destinationLocationId||'Unscoped (legacy)')}</td>
      <td>${esc(route?route.group+' · '+route.distanceRange:'All point routes')}</td>
      <td>${esc(r.factorValue)} ${esc(r.factorUnit)}</td>
      <td>${esc(r.shift||'All')} / ${esc(r.vehicleClass||'All classes')}</td>
      <td>${esc(r.effectiveFrom)}${r.effectiveTo?' – '+esc(r.effectiveTo):''}</td>
      <td>${esc(r.referenceNo||'—')}</td><td>${esc(r.status)}</td>
      <td>${r.status==='DRAFT'?'<button class="btn outline" onclick="decideFactor(\''+esc(r.factorId)+'\',\'APPROVE\')">Approve</button>':'—'}</td></tr>`;
  });
  const html=pageHead('MCL Quantity Rules','Destination-specific Coal MT/trip and OB CuM/trip averages with optional route, shift and vehicle class.')+
    context()+panel('Create MCL average',form,'Approval required')+
    panel('Approved & draft rule register',recentTable(['Type','Material','Unloading','Route / Distance','Average','Shift / Class','Effective','MCL Ref','Status','Action'],items),rules.length+' rules');
  // Called after the page has mounted; populate dependant master dropdowns.
  queueMicrotask(()=>{if($('pfKind'))koPointChangeKind()});
  return html;
}
async function koPointSaveRule(){
  try{
    const kind=$('pfKind').value,val=$('pfValue').value;
    if(!val||!Number.isFinite(Number(val))||Number(val)<=0)throw Error('Enter a positive approved average.');
    if(!$('pfDest').value||!$('pfMaterial').value)throw Error('Choose unloading point and material.');
    const ref=$('pfRef').value.trim();
    if(!ref)throw Error('Enter the MCL source reference.');
    const body={
      factorType:koPointKinds[kind],factorValue:val,factorUnit:koUnit(kind),
      destinationLocationId:$('pfDest').value,routeId:$('pfRoute').value||null,
      materialId:$('pfMaterial').value,effectiveFrom:$('pfFrom').value,
      effectiveTo:$('pfTo').value||null,operatingDate:$('pfOpDate').value||null,
      shift:$('pfShift').value||null,vehicleClass:$('pfClass').value.trim()||null,
      referenceNo:ref,sourceOrg:'MCL'
    };
    await api('/api/sites/KOCP/weight-factors',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    toast('Point-wise MCL rule saved as draft. Approval is required.');
    await render();
  }catch(e){toast(e.message,'bad')}
}
async function renderKocpPointReport(from,to){
  const day=state.ctx.operatingDate;
  from=from||day.slice(0,8)+'01';to=to||day;
  const p=new URLSearchParams({from_date:from,to_date:to});
  const data=await api('/api/site-ops/KOCP/reports/point-wise?'+p.toString());
  function grid(rows){
    return recentTable(['Date','Shift','Material','Unloading point','Movement / Distance','Trips','Quantity','Weighted avg/trip','No MCL factor'],rows.map(x=>
      `<tr><td>${esc(x.date||'TOTAL')}</td><td>${esc(x.shift||'All')}</td><td>${esc(x.material)}</td>
       <td>${esc(x.destination)}</td><td>${esc(x.movement)} · ${esc(x.distance)}</td>
       <td>${fmt(x.trips)}</td><td>${fmt(x.quantity,3)} ${esc(x.unit)}</td>
       <td>${x.weightedAverage===null?'—':fmt(x.weightedAverage,3)+' '+esc(x.unit)+'/trip'}</td>
       <td>${x.missingFactorTrips?'<span class="status warn">'+fmt(x.missingFactorTrips)+'</span>':'—'}</td></tr>`));
  }
  function summary(kind){
    const rows=data.pointSummary.filter(x=>x.kind===kind),t=data.totals[kind];
    const unit=kind==='OB'?'CuM':'MT';
    return panel((kind==='OB'?'OB':'Coal / Reject')+' — Unloading point summary',
      '<p class="simple-note">Total '+fmt(t.trips)+' trips · '+fmt(t.quantity,3)+' '+unit+
      ' · Weighted average '+(t.weightedAverage===null?'—':fmt(t.weightedAverage,3))+' '+unit+'/trip</p>'+
      grid(rows),rows.length+' combinations');
  }
  const details=data.dailyShift.length>1000
    ?'<p class="simple-note">Showing first 1,000 shift rows; narrow the date range to see the remaining '+(data.dailyShift.length-1000)+' records.</p>':'';
  const form=`<div class="toolbar"><label>From <input id="koReportFrom" type="date" value="${esc(from)}"></label>
    <label>To <input id="koReportTo" type="date" value="${esc(to)}"></label>
    <button class="btn primary" onclick="koPointReloadReport()">Show Report</button></div>`;
  return pageHead('KOCP Point-wise Production Report','Calculated from posted Coal and OB trips. MT and CuM remain separate.')+
    context()+panel('Reporting period',form)+summary('COAL')+summary('OB')+
    panel('Date & shift details',details+grid(data.dailyShift.slice(0,1000)),data.dailyShift.length+' groups');
}
async function koPointReloadReport(){
  try{$('workspace').innerHTML=await renderKocpPointReport($('koReportFrom').value,$('koReportTo').value);}
  catch(e){toast(e.message,'bad')}
}
window.koPointChangeKind=koPointChangeKind;
window.koPointChangeDestination=koPointChangeDestination;
window.koPointChangeRoute=koPointChangeRoute;
window.koPointSaveRule=koPointSaveRule;
window.koPointReloadReport=koPointReloadReport;
window.renderFactor=renderKocpPointFactors;
