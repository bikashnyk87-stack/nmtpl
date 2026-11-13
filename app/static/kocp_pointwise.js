/* KOCP unloading-point MCL factors, approved rule calculation and reporting.
   All values are loaded from the existing KOCP masters, never hardcoded. */
const koPointState={routes:[],materials:{COAL:[],OB:[]},rules:[],vehicleClasses:[]};
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
function koFactorClassesFromEquipment(rows){
  const options=new Set(['EICHER','BHARAT BENZ','TATA','VOLVO TIPPER','VOLVO','ASHOK LEYLAND']);
  for(const x of rows||[]){
    if(!x.active)continue;
    const kind=String(x.type||'').trim().toUpperCase();
    const name=(kind+' '+String(x.makeModel||'')).toUpperCase();
    if(kind&&kind!=='OTHER'&&/(TIPPER|TRIPPER|DUMPER|TRUCK)/.test(kind))options.add(kind);
    for(const brand of ['EICHER','BHARAT BENZ','TATA','VOLVO','ASHOK LEYLAND']){
      if(name.includes(brand))options.add(brand);
    }
  }
  return [...options].sort();
}
function koPointSourceChanged(){
  const final=$('pfSource')?.value==='MCL_MONTHLY';
  if($('pfOpDate')){$('pfOpDate').disabled=final;if(final)$('pfOpDate').value=''}
  if($('pfShift')){$('pfShift').disabled=final;if(final)$('pfShift').value=''}
  const hint=$('pfSourceHint');
  if(hint)hint.textContent=final
    ?'Final approved MCL month-end averages re-rate trips for billing only. They never change saved operational trips. Set the full period and MCL document reference.'
    :'Approved daily provisional averages are used when posting Coal/OB trips. The final MCL month-end report controls billing separately.';
}
function koPointName(id,list,key,label){
  const found=list.find(x=>x[key]===id);return found?found[label]:id||'—';
}
async function renderKocpPointFactors(options={}){
  const final=options.final===true;
  const [rules,routes,catalog,equipment]=await Promise.all([
    api('/api/sites/KOCP/weight-factors'),
    api('/api/sites/KOCP/routes'),
    api('/api/sites/KOCP/material-types'),
    api('/api/sites/KOCP/factor-vehicle-classes')
  ]);
  koPointState.rules=rules;koPointState.routes=routes;
  koPointState.materials=catalog;
  koPointState.vehicleClasses=equipment;
  const date=state.ctx.operatingDate;
  const form=`<p class="simple-note">${final
    ?'Enter final month-end MCL-approved averages by unloading point, material and vehicle class here. These are used to prepare billing and do not change daily production entries. The certified monthly total is entered and approved separately above.'
    :'Enter daily operating averages by unloading point, material and vehicle class. These are provisional production rates and never become final billable values without monthly MCL certification.'}</p>
    <div class="form-grid">
      <input id="pfSource" type="hidden" value="${final?'MCL_MONTHLY':'DAILY_REPORT'}">
      <div class="field"><span>Average purpose</span><strong>${final?'Final monthly MCL average · billing':'Daily operational average · production'}</strong></div>
      <div class="field"><span>Material type</span><select id="pfKind" onchange="koPointChangeKind()">
        <option value="COAL">Coal / Reject (MT)</option><option value="OB">OB (CuM)</option></select></div>
      <div class="field"><span>Unloading point *</span><select id="pfDest" onchange="koPointChangeDestination()">${koPointOpts(koPointDestinations("COAL"),"id","name","Choose unloading point")}</select></div>
      <div class="field"><span>Route / distance (optional)</span><select id="pfRoute" onchange="koPointChangeRoute()"></select></div>
      <div class="field"><span>Material *</span><select id="pfMaterial">${koPointOpts(koPointMaterials("COAL"),"materialId","name","Choose material")}</select></div>
      <div class="field"><span>Approved average / trip *</span><input id="pfValue" type="number" step="0.000001" min="0.000001" placeholder="Enter MCL-approved value"></div>
      <div class="field"><span>Unit</span><strong id="pfUnit">MT/TRIP</strong></div>
      <div class="field"><span>${final?'MCL certified period start *':'Effective from *'}</span><input id="pfFrom" type="date" value="${final?date.slice(0,8)+'01':date}"></div>
      <div class="field"><span>${final?'Month-end period end *':'Effective to (optional)'}</span><input id="pfTo" type="date" ${final?'required':''}></div>
      ${final?'':'<div class="field"><span>Operating date (optional)</span><input id="pfOpDate" type="date"></div>'}
      ${final?'':'<div class="field"><span>Shift</span><select id="pfShift"><option value="">All shifts</option>'+state.ctx.shifts.map(s=>'<option value="'+esc(s.shift)+'">'+esc(s.shift)+'</option>').join('')+'</select></div>'}
      <div class="field"><span>Vehicle / dumper class</span><select id="pfClass"><option value="">All vehicle types</option>${koPointState.vehicleClasses.map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join('')}</select><small>Choose Eicher, Bharat Benz, Tata, Volvo or a master type; one average can differ by vehicle class.</small></div>
      <div class="field"><span>${final?'MCL monthly certificate reference *':'Daily production report reference *'}</span><input id="pfRef" maxlength="120" placeholder="${final?'MCL approved report / circular':'Daily report number or sheet reference'}"></div>
      <div class="form-actions"><button class="btn primary" onclick="koPointSaveRule()">Create Draft</button></div>
    </div>`;
  const dests=[...koPointDestinations('COAL'),...koPointDestinations('OB')];
  const visibleRules=rules.filter(r=>final?r.sourceOrg==='MCL_MONTHLY':r.sourceOrg!=='MCL_MONTHLY');
  const items=visibleRules.map(r=>{
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
      <td>${esc(r.sourceOrg==='MCL_MONTHLY'?'MCL final':r.sourceOrg==='DAILY_REPORT'?'Daily provisional':'Legacy operational')}</td>
      <td>${esc(r.referenceNo||'—')}</td><td>${esc(r.status)}</td>
      <td>${r.status==='DRAFT'?'<button class="btn outline" onclick="decideFactor(\''+esc(r.factorId)+'\',\'APPROVE\')">Approve</button>':'—'}</td></tr>`;
  });
  const entry=panel(final?'Enter final MCL monthly average':'Enter daily operating average',form,'Approval required');
  const register=panel(final?'MCL monthly-average register':'Daily operating-average register',
    recentTable(['Material type','Material','Unloading','Route / Distance','Average','Shift / Class','Effective','Purpose','Report Ref','Status','Action'],items),
    visibleRules.length+' rules');
  if(final)return entry+register;
  return pageHead('MCL Quantity Rules','Daily Coal MT/trip and OB CuM/trip production averages by unloading point, route and vehicle class.')+
    context()+entry+register;
}
async function koPointSaveRule(){
  try{
    const kind=$('pfKind').value,val=$('pfValue').value;
    if(!val||!Number.isFinite(Number(val))||Number(val)<=0)throw Error('Enter a positive approved average.');
    if(!$('pfDest').value||!$('pfMaterial').value)throw Error('Choose unloading point and material.');
    const ref=$('pfRef').value.trim();
    if(!ref)throw Error('Enter the MCL source reference.');
    const source=$('pfSource').value;
    const from=$('pfFrom').value,to=$('pfTo').value;
    if(source==='MCL_MONTHLY'&&(!from||!to))throw Error('Final MCL average needs start and end dates.');
    if(to&&to<from)throw Error('Effective end date must not precede the start.');
    const body={
      factorType:koPointKinds[kind],factorValue:val,factorUnit:koUnit(kind),
      destinationLocationId:$('pfDest').value,routeId:$('pfRoute').value||null,
      materialId:$('pfMaterial').value,effectiveFrom:$('pfFrom').value,
      effectiveTo:$('pfTo').value||null,operatingDate:$('pfOpDate')?.value||null,
      shift:$('pfShift')?.value||null,vehicleClass:$('pfClass').value.trim()||null,
      referenceNo:ref,sourceOrg:source
    };
    await api('/api/sites/KOCP/weight-factors',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    toast((source==='MCL_MONTHLY'?'Final MCL monthly':'Daily operational')+' factor draft saved. Approval required.');
    await render();
  }catch(e){toast(e.message,'bad')}
}
let koPointReportData=null;
function koPointCategoryTable(rows){
  return recentTable(
    ['Coal / OB','Material','Unloading point','Movement','Equipment category','Vehicle make / class','Ownership','Trips','Quantity','Weighted average'],
    (rows||[]).map(x=>`<tr><td>${esc(x.kind)}</td><td>${esc(x.material)}</td>
      <td>${esc(x.destination)}</td><td>${esc(x.movement)}</td><td>${esc(x.equipmentCategory)}</td>
      <td>${esc(x.vehicleClass)}</td><td>${esc(x.ownership)}</td><td>${fmt(x.trips)}</td>
      <td>${fmt(x.quantity,3)} ${esc(x.unit)}</td>
      <td>${x.weightedAverage==null?'—':fmt(x.weightedAverage,3)+' '+esc(x.unit)+'/trip'}</td></tr>`)
  );
}
function koPointDownloadCategoryCsv(){
  const data=koPointReportData;
  if(!data)return toast('Open the category report first.','bad');
  const quote=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
  const rows=[
    ['KOCP OPERATIONAL CATEGORY SUMMARY — NOT FINAL MCL BILLING'],
    ['From',data.fromDate,'To',data.toDate],
    ['Kind','Material','Destination','Movement','Equipment Category','Vehicle Class','Ownership','Trips','Quantity','Unit','Weighted Average'],
    ...(data.categorySummary||[]).map(r=>[
      r.kind,r.material,r.destination,r.movement,r.equipmentCategory,
      r.vehicleClass,r.ownership,r.trips,r.quantity,r.unit,r.weightedAverage,
    ]),
  ];
  const csv='\uFEFF'+rows.map(row=>row.map(quote).join(',')).join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  const el=document.createElement('a');el.href=url;
  el.download='KOCP_Operational_Category_'+data.fromDate+'_to_'+data.toDate+'.csv';
  document.body.appendChild(el);el.click();el.remove();URL.revokeObjectURL(url);
}
async function renderKocpPointReport(from,to){
  const day=state.ctx.operatingDate;
  from=from||day.slice(0,8)+'01';to=to||day;
  const p=new URLSearchParams({from_date:from,to_date:to});
  const data=await api('/api/site-ops/KOCP/reports/point-wise?'+p.toString());
  koPointReportData=data;
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
    <button class="btn primary" onclick="koPointReloadReport()">Show Report</button>
    <button class="btn outline" onclick="koPointDownloadCategoryCsv()">Download Category CSV</button></div>`;
  return pageHead('KOCP Point-wise Production Report','Calculated from posted Coal and OB trips. MT and CuM remain separate.')+
    context()+panel('Reporting period',form)+summary('COAL')+summary('OB')+
    panel('Date & shift details',details+grid(data.dailyShift.slice(0,1000)),data.dailyShift.length+' groups')+
    panel('Category-wise Coal and OB summary',
      '<p class="simple-note">Physical machine categories and ownership aliases are standardized for reporting. Coal is in MT, OB in CuM. These remain <b>operating quantities</b>; final billable figures are set only in Billing using approved MCL monthly factors or survey.</p>'+
      koPointCategoryTable(data.categorySummary||[]),
      (data.categorySummary||[]).length+' category combinations');
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
window.renderKocpPointReport=renderKocpPointReport;
window.renderFactor=renderKocpPointFactors;
window.renderKocpPointFactors=renderKocpPointFactors;

window.koPointSourceChanged=koPointSourceChanged;

window.koPointDownloadCategoryCsv=koPointDownloadCategoryCsv;
