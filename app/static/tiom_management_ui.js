/* TIOM management screens — single-source, read-only presentation layer.
   Loaded AFTER Phase 1 so the legacy welcome splash cannot overwrite Overview. */
(function(){
  'use strict';
  const E = x => esc(x == null ? '' : String(x));
  const v = id => { const el=document.getElementById(id);return el?el.value:''; };
  const fmt = (x,d=1,unit='') => (x == null || x === '') ? '—' : Number(x).toLocaleString('en-IN',{minimumFractionDigits:d,maximumFractionDigits:d})+unit;
  const pct = (x,d=0) => x == null ? '—' : fmt(x,d,'%');
  const arr = x => Array.isArray(x) ? x : [];
  const cell = (v) => E(v);
  const box = (title,inner,sub='') => '<section class="mc-panel"><div class="mc-section-head"><b>'+E(title)+'</b>'+(sub?'<small>'+E(sub)+'</small>':'')+'</div><div class="mc-panel-body">'+inner+'</div></section>';
  const metric = (label,value,subtitle,accent='',icon='') => '<div class="mc-metric '+E(accent)+'">'+
       (icon?'<div class="mc-symbol">'+icon+'</div>':'')+
       '<span>'+E(label)+'</span><strong>'+E(value)+'</strong><small>'+E(subtitle||'')+'</small></div>';
  const tbl = (heads,rows) => '<div class="mc-table-wrap"><table class="mc-table"><thead><tr>'+heads.map(x=>'<th>'+E(x)+'</th>').join('')+'</tr></thead><tbody>'+
      (rows.length?rows.map(c=>'<tr>'+c.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join(''):'<tr><td colspan="'+heads.length+'" class="mc-empty">No recorded data for this period</td></tr>')+
      '</tbody></table></div>';
  const status = (yes,label) => '<span class="mc-status '+(yes?'mc-ok':'mc-pending')+'">'+(yes?'● ':'● ')+E(label)+'</span>';
  const attention = (title,detail,amount,tone='warn') => '<button class="mc-attention '+E(tone)+'" onclick="render('+"'DASHBOARD'"+')"><span class="mc-att-icon">'+(tone==='danger'?'!':'!')+'</span><span><b>'+E(title)+'</b><small>'+E(detail)+'</small></span><strong>'+E(amount)+' →</strong></button>';

  function trend(rows, keys) {
    const data=arr(rows).slice(-7), W=800,H=205,left=46,top=18,plotH=152;
    if(!data.length)return '<p class="mc-empty">No production trend entries for this period</p>';
    const max=Math.max(1,...data.map(x=>Math.max(...keys.map(k=>Number(x[k.key]||0)))));
    const y=v=>top+plotH*(1-v/max), groupW=(W-left-15)/data.length;
    let grid=''; for(let i=0;i<=4;i++){const q=max*i/4,py=y(q);grid+='<line x1="'+left+'" y1="'+py+'" x2="'+(W-10)+'" y2="'+py+'" class="mc-chart-grid"/><text x="'+(left-7)+'" y="'+(py+4)+'" text-anchor="end">'+Math.round(q).toLocaleString('en-IN')+'</text>';}
    let bars=''; data.forEach((x,i)=>{const base=left+i*groupW+groupW*.16; keys.forEach((k,j)=>{const value=Math.max(0,Number(x[k.key]||0)),width=groupW*.3,xpos=base+j*width*1.05;bars+='<rect x="'+xpos+'" y="'+y(value)+'" width="'+width+'" height="'+Math.max(0,top+plotH-y(value))+'" rx="2" fill="'+k.color+'"><title>'+E(x.date||'')+' — '+E(k.title)+' '+fmt(value,1,' t')+'</title></rect>';});bars+='<text x="'+(left+i*groupW+groupW*.5)+'" y="'+(H-11)+'" text-anchor="middle">'+E(String(x.date||'').slice(5))+'</text>';});
    return '<div class="mc-chart-legend">'+keys.map(k=>'<span><i style="background:'+k.color+'"></i>'+E(k.title)+'</span>').join('')+'</div>'+
      '<svg class="mc-trend" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="7-day trend chart">'+grid+bars+'</svg>';
  }
  function fuelChart(d) {
    const groups={}, lookups=[['TRUCK','Trucks'],['DUMPER','Trucks'],['TIPPER','Trucks'],['EXCAV','Excavators'],['DRILL','Drilling'],['LOADER','Loaders']];
    arr(d.fuelByEquipment).forEach(x=>{
      const text=String(x.type||'').toUpperCase();
      const found=lookups.find(q=>text.includes(q[0]));
      const group=found?found[1]:'Other';
      groups[group]=(groups[group]||0)+Number(x.litres||0);
    });
    const values=Object.entries(groups).sort((a,b)=>b[1]-a[1]),max=Math.max(1,...values.map(x=>x[1]));
    return values.length?'<div class="mc-horizontal-bars">'+values.map(x=>
      '<div class="mc-bar-row"><span>'+E(x[0])+'</span><div class="mc-bar-track"><i style="width:'+Math.round(x[1]/max*100)+'%"></i></div><b>'+fmt(x[1],0,' L')+'</b></div>').join('')+'</div>':
      '<p class="mc-empty">No HSD issues recorded in the selected period</p>';
  }
  function equipmentTable(d,mode) {
    const fuel=Object.fromEntries(arr(d.fuelByEquipment).map(x=>[String(x.machine||''),x.litres]));
    let list = mode==='VEHICLES' ? arr(d.misVehicles).map(x=>({id:x.vehicle,trips:x.trips,tonnes:x.tonnes})) :
       arr(d.misMachines).map(x=>({id:x.machine,trips:x.trips,tonnes:x.tonnes}));
    if(!list.length && mode==='VEHICLES')list=arr(d.vehicles).map(x=>({id:x.vehicle,trips:x.trips,tonnes:x.tonnes}));
    if(!list.length && mode!=='VEHICLES')list=[...arr(d.loaders),...arr(d.excavators)].map(x=>({id:x.machine,trips:x.trips,tonnes:x.tonnes}));
    return tbl(['Equipment','Trips','Handled quantity','HSD issued'],list.slice(0,7).map(x=>[
      '<b>'+E(x.id||'—')+'</b>',fmt(x.trips,0),fmt(x.tonnes,1,' t'),fuel[x.id]==null?'—':fmt(fuel[x.id],1,' L')]));
  }
  function plantTable(d,compact=false){
    return tbl(compact?['Plant','Feed t','Output t','Run h','Feed t/h']:['Plant','Feed t','Gross output t','Run h','Feed t/h','Status'],
      arr(d.plantPerformance).map(x=>{
        const pending=x.plantType==='CRUSHER' && !!d.production?.allocationPending;
        const output=pending?'Gross '+fmt(x.grossOutputMt,1):fmt(x.grossOutputMt??x.outputMt,1);
        const feed=fmt(x.grossThroughputMt??x.feedMt,1);
        const row=['<b>'+E(x.plant)+'</b>',feed,output,fmt(x.runningHours,1),fmt(x.tph,1)];
        if(!compact)row.push(pending?status(false,'Fresh allocation pending'):x.runningHours==null?status(false,'HMR not recorded'):status(true,'Recorded'));
        return row;
      }));
  }
  function ownerView(d) {
    const p=d.production||{},k=d.kpis||{},br=d.breakdowns||{},dr=d.drilling?.totals||{};
    const hs=S.tiomOwnerHsd||null;const isPending=!!p.allocationPending;
    const cards=[
      metric('FRESH ROM',fmt(p.romInputMt,1,' t'),'Mine-origin movement','teal'),
      metric('OB REMOVED',fmt(k.obRemovedMt??k.wasteTonnes??k.misObQty,1,' t'),'Confirmed WB weight · MIS fallback for legacy shifts','blue'),
      metric('FRESH OUTPUT',isPending?'Allocation pending':fmt(p.finalProductionMt,1,' t'),isPending?'Crusher feed evidence required':'Recorded / allocated','amber'),
      metric('REHANDLING',fmt(p.oldStockExcludedMt,1,' t'),'Excluded from fresh output','blue'),
      metric('HSD ISSUED',fmt(k.hsdLitres,1,' L'),'Selected period','green'),
      metric('FUEL BOOK BALANCE',hs?fmt(hs.closingBook,1,' L'):'—',hs?'Latest HSD book for '+E(d.toDate):'Open HSD for verified stock','blue')
    ].join('');
    const attentionRows=[
      p.allocationPending?attention('Crusher allocation incomplete','Gross output known; fresh-share feed tonnage unverified','Review','warn'):'',
      Number(d.exceptionDetails?.leadTotal||0)?attention('Trips with lead unresolved','Review route + exact bench in existing Masters',d.exceptionDetails.leadTotal,'warn'):'',
      Number(d.exceptionDetails?.tonnageTotal||0)?attention('Trips awaiting weight','WB weight or approved trip factor not available',d.exceptionDetails.tonnageTotal,'warn'):'',
      Number(br.activeEvents||0)?attention('Machine breakdowns open','Reported in Mechanical maintenance ledger',br.activeEvents,'danger'):'',
      Number(k.misDrafts||0)?attention('MIS reports in draft','Submitted reports alone contribute to operational report',k.misDrafts,'warn'):'',
      Number(k.wbUnmatched||0)?attention('WB movements not linked to MIS','WB tonnes remain included; attribution needs review',k.wbUnmatched,'warn'):''
    ].filter(Boolean);
    const period=E(d.fromDate)+(d.toDate!==d.fromDate?' – '+E(d.toDate):'');
    const drill=metric('ROM/OB HOLES',fmt(dr.romObHoles,0),'Separated hole entry')+
      metric('BHJ/BHQ HOLES',fmt(dr.bhjBhqHoles,0),'Separated hole entry')+
      metric('ROM/OB METERS',fmt(dr.romObMeterage,1,' m'),'Drill meterage')+
      metric('BHJ/BHQ METERS',fmt(dr.bhjBhqMeterage,1,' m'),'Drill meterage')+
      metric('UNCLASSIFIED HOLES',fmt(dr.unclassifiedHoles,0),'Historical combined counts')+
      metric('DRILL RATE',fmt(k.drillMeterPerHour,1,' m/h'),'Valid HMR only');
    const footer='<div class="mc-checks">'+status(Number(k.wbTrips)>0,'Confirmed WB: '+fmt(k.wbTrips,0)+' movements')+
      status(Number(k.misDrafts||0)===0,'MIS drafts: '+fmt(k.misDrafts,0))+
      status(Number(k.haulLeadMissingTrips||0)===0,'Lead unresolved: '+fmt(k.haulLeadMissingTrips,0))+'</div>';
    const mode=S.tiomEquipMode||'MACHINES';
    const tabs='<div class="mc-tabline"><button class="'+(mode==='MACHINES'?'active':'')+'" onclick="tiomEquipMode('+"'MACHINES'"+')">Excavators / Loaders</button>'+
      '<button class="'+(mode==='VEHICLES'?'active':'')+'" onclick="tiomEquipMode('+"'VEHICLES'"+')">Vehicles</button></div>';
    html('owner_body','<div class="mc-owner-kpis">'+cards+'</div>'+
      '<div class="mc-owner-main">'+
      box('Work achieved — 7-day trend',trend(d.sevenDay,[{key:'romInput',title:'Fresh ROM',color:'#008f86'},{key:'finalProduction',title:'Calculated final output',color:'#158dbc'}]),
        'Movement categories shown separately · '+period)+
      box('Owner attention','<div class="mc-attentions">'+(attentionRows.length?attentionRows.join(''):'<p class="mc-empty">No flagged exceptions for this selection</p>')+'</div>','Supporting records open in Dashboard')+
      box('Equipment performance',tabs+equipmentTable(d,mode),'WB-linked and submitted MIS activity; not additional fresh output')+
      box('Fuel issued by activity',fuelChart(d),'Issued quantity, not verified fuel consumption')+
      box('Plant performance',plantTable(d,true),'Gross plant movement and run-hour evidence')+
      box('Drilling & entry completeness','<div class="mc-three">'+drill+'</div>'+footer,'Blank/missing meter readings are not zero')+
      '</div><p class="mc-caveat">Owner Overview summarizes the live TIOM records. Quantities shown as pending are not treated as confirmed. Source-based entries are not counted twice.</p>');
  }
  window.tiomEquipMode=function(mode){S.tiomEquipMode=mode; if(S.tiomOwnerData)ownerView(S.tiomOwnerData);};
  function setupOwner() {
    const today=E(S.boot.today);
    html('app','<div class="mc-shell mc-owner"><div class="mc-page-head"><div><h1>Owner Overview</h1><p>Work achieved · Resources used · Decisions needed</p></div>'+
      '<div class="mc-head-filters"><select id="mc_period" aria-label="Overview reporting period" onchange="tiomOwnerPeriod()">'+
      '<option value="TODAY">Today</option><option value="YESTERDAY">Yesterday</option><option value="7D">7 days</option><option value="MTD">MTD</option><option value="CUSTOM">Custom</option></select>'+
      '<label id="mc_from_label" hidden>From<input id="mc_from" type="date" value="'+today+'"></label>'+
      '<label id="mc_to_label" hidden>To<input id="mc_to" type="date" value="'+today+'"></label>'+
      '<select id="mc_shift" aria-label="Shift" onchange="tiomOwnerLoad()"><option value="ALL">All shifts</option>'+
      opt(S.boot.masters.shifts,x=>x,x=>x)+'</select>'+
      '<label>Material<input id="mc_material" placeholder="All materials" size="12"></label><label>Source<input id="mc_source" placeholder="All sources" size="12"></label><label>Destination<input id="mc_destination" placeholder="All destinations" size="12"></label><label>Vehicle<input id="mc_vehicle" placeholder="All vehicles" size="12"></label>'+ 
      '<button class="btn secondary small" onclick="tiomOwnerLoad()">Refresh</button>'+
      '<button class="btn primary small" onclick="render('+"'DASHBOARD'"+')">Detailed Dashboard →</button></div></div>'+
      '<div id="owner_body" class="mc-loading">Loading management figures…</div></div>');
    window.tiomOwnerPeriod();
  }
  window.tiomOwnerPeriod=function(){
    const custom=v('mc_period')==='CUSTOM';
    for(const id of ['mc_from_label','mc_to_label']){const el=document.getElementById(id);if(el)el.hidden=!custom;}
    tiomOwnerLoad();
  };
  window.tiomOwnerLoad=function(){
    const mode=v('mc_period')||'TODAY';
    S.tiomOwnerHsd=null;
    appRun(d=>{
      S.tiomOwnerData=d; ownerView(d);
      if(arr(S.boot.user.modules).includes('HSD') && d.fromDate===d.toDate){
        appRun(h=>{if(S.screen!=='HOME' || S.tiomOwnerData!==d)return; S.tiomOwnerHsd=h.entrySummary||null; ownerView(d);},
          ()=>{}).getTiomHsdDesk({date:String(d.toDate),shift:S.boot.shift,reportFrom:String(d.fromDate),reportTo:String(d.toDate)});
      }
    },e=>html('owner_body','<div class="panel bad">'+E(e.message)+' <button class="btn secondary" onclick="tiomOwnerLoad()">Retry</button></div>')).getDashboard({
      mode,fromDate:v('mc_from'),toDate:v('mc_to'),shift:v('mc_shift')||'ALL',materialFilter:v('mc_material'),sourceFilter:v('mc_source'),destinationFilter:v('mc_destination'),vehicleFilter:v('mc_vehicle')
    });
  };
  window.renderHome=setupOwner;

  // Compact, evidence-based operations summary. All existing detailed reports
  // remain rendered underneath in the original workspace.js.
  window.tiomRefDetailed=function(d) {
    const p=d.production||{},k=d.kpis||{},br=d.breakdowns||{},unverified=!!p.allocationPending;
    const metrics=[
      metric('Fresh ROM',fmt(p.romInputMt,1,' t'),'Mine-origin material','teal','◆'),
      metric('Plant feed',fmt(p.plantFeedMt,1,' t'),'Weighed/recorded feed','blue','⇢'),
      metric('Screen final',fmt(p.screenDirectMt,1,' t'),'Screen output','blue','▲'),
      metric('Crusher gross',fmt(p.crusherGrossOutputMt,1,' t'),'Physical output','blue','⚙'),
      metric('Fresh crusher output',unverified?'Pending':fmt(p.crusherFreshOutputMt,1,' t'),unverified?'Feed allocation required':'Fresh share of gross','amber','▣'),
      metric('Final fresh output',unverified?'Pending':fmt(p.finalProductionMt,1,' t'),unverified?'Allocation incomplete':'Fresh final total','amber','▲'),
      metric('OB removed',fmt(k.obRemovedMt??k.wasteTonnes??k.misObQty,1,' t'),'Confirmed WB weight · MIS fallback for legacy shifts','blue','◩'),
      metric('Rehandling',fmt(p.oldStockExcludedMt,1,' t'),'Excluded from fresh production','blue','⟳')
    ].join('');
    const fresh=fmt(p.romInputMt,1,' t'),feed=fmt(p.plantFeedMt,1,' t'),screen=fmt(p.screenDirectMt,1,' t'),crusher=fmt(p.crusherGrossOutputMt,1,' t');
    const flow='<div class="mc-flow">'+
      '<div class="mc-flow-node"><span>Fresh ROM</span><strong>'+fresh+'</strong></div><div class="mc-flow-arrow">→</div>'+
      '<div class="mc-flow-node"><span>MSP feed</span><strong>'+feed+'</strong></div><div class="mc-flow-arrow">→</div>'+
      '<div class="mc-flow-split"><div class="mc-flow-node"><span>Screen final output</span><strong>'+screen+'</strong></div>'+
      '<div class="mc-flow-node"><span>Intermediate to crusher</span><strong>'+(p.crusherFeedMt>0?fmt(p.crusherFeedMt,1,' t'):'Quantity pending')+'</strong></div></div>'+
      '<div class="mc-flow-arrow">→</div><div class="mc-flow-node"><span>Crusher gross output</span><strong>'+crusher+'</strong></div>'+
      '<div class="mc-flow-arrow">→</div><div class="mc-flow-node final"><span>Fresh output</span><strong>'+(unverified?'Pending':fmt(p.finalProductionMt,1,' t'))+'</strong></div></div>'+
      '<div class="mc-flow-alert">Old-stock movements: <b>'+fmt(p.oldStockExcludedMt,1,' t')+'</b> &nbsp;|&nbsp; Recorded blend feed: <b>'+fmt(p.crusherBlendFeedMt,1,' t')+'</b> &nbsp;|&nbsp; '+(unverified?'Fresh crusher allocation requires verified feed quantity':'Allocation follows the recorded feed mix')+'</div>';
    const wb=Math.max(0,Number(k.wbTrips||0)),linked=Math.max(0,Number(k.misWbLinkedTrips||0)),field=Math.max(0,Number(k.matched||0));
    const frac=(a,b)=>b>0?Math.min(100,a/b*100):0;
    const recon='<div class="mc-recon-kpis">'+
        metric('WB valid',fmt(wb,0),'Movements','blue')+metric('WB ↔ MIS linked',fmt(linked,0),'Trips','blue')+
        metric('WB ↔ Field matched',fmt(field,0),'Exact matches','blue')+'</div>'+
      '<div class="mc-progress"><span>MIS coverage '+pct(frac(linked,wb))+'</span><div><i style="width:'+frac(linked,wb)+'%"></i></div></div>'+
      '<div class="mc-progress"><span>Field match coverage '+pct(frac(field,wb))+'</span><div><i style="width:'+frac(field,wb)+'%"></i></div></div>'+
      '<div class="mc-reviewline">WB without MIS link: '+fmt(k.wbUnmatched,0)+' movements</div>'+
      '<div class="mc-reviewline">MIS trips requiring lead: '+fmt(k.leadMissingTrips,0)+' trips</div>'+
      '<small>Coverage categories overlap; matching links are not added as production.</small>';
    const machineRows=arr(d.misMachines).slice(0,5),fuel=Object.fromEntries(arr(d.fuelByEquipment).map(x=>[String(x.machine||''),x.litres]));
    const equip=tbl(['Equipment','Trips','Handled t','HSD L'],machineRows.map(x=>[
      '<b>'+E(x.machine||'—')+'</b>',fmt(x.trips,0),fmt(x.tonnes,1),fuel[x.machine]==null?'—':fmt(fuel[x.machine],1)]));
    const hs=metric('HSD issued',fmt(k.hsdLitres,1,' L'),'Selected operating period','blue')+metric('Fuel consumed','Not available','Issues are not consumption','blue');
    const bd=tbl(['Machine','Fault','Downtime h','Status'],arr(br.rows).slice(0,5).map(x=>[
      '<b>'+E(x.machine)+'</b>',E(x.fault),fmt(x.periodDowntimeHours,1),status(!x.isOpen,x.status)]));
    const shifts=tbl(['Shift','WB trips','Tonnes','HSD L'],arr(d.shiftComparison).map(x=>[
      '<b>'+E(x.shift)+'</b>',fmt(x.trips,0),fmt(x.tonnes,1),fmt(x.fuel,1)]));
    return '<div class="mc-dashboard-presentation"><div class="mc-dash-metrics">'+metrics+'</div>'+
      box('Production flow & allocation',flow,'Fresh output is shown only where allocation evidence is complete')+
      '<div class="mc-dash-main">'+box('Plant feed vs output',plantTable(d,false),'Plant-level physical movement and actual HMR')+
      box('Movement reconciliation',recon,'Confirmed WB is authoritative for weighed movements')+
      box('Equipment & vehicle performance',equip,'Submitted MIS equipment attribution; further drilldowns below')+
      box('HSD — selected operating period','<div class="mc-recon-kpis">'+hs+'</div>'+fuelChart(d),'Issued quantities from central ledger')+
      box('Machine breakdown report','<div class="mc-mini-strip">'+metric('Open events',fmt(br.activeEvents,0),'Recorded maintenance','amber')+
        metric('Period downtime',fmt(br.periodDowntimeHours,1,' h'),'Shift overlap','blue')+'</div>'+bd,'From Mechanical ledger')+
      box('Shift comparison',shifts,'WB and issued fuel, shift by shift')+
      '</div></div>';
  };

  // Management-first navigation. Specialized MIS and drilling are existing
  // Production subtabs, not duplicate records or new separate modules.
  window.tiomGoNav=function(name){
    if(name==='MIS'){render('PRODUCTION');tiomProdTab('SAVED');}
    else if(name==='DRILL'){render('PRODUCTION');tiomProdTab('DRILL');}
    else render(name);
    if(name==='MIS'||name==='DRILL'){
      document.querySelectorAll('#nav button').forEach(x=>{x.classList.remove('active');x.setAttribute('aria-current',x.id==='nav_'+name?'page':'false');});
      const el=document.getElementById('nav_'+name);if(el)el.classList.add('active');
    }
  };
  window.buildNav=function(){
    const modules=arr(S.boot.user.modules),management=!!S.boot.user.isManagement;
    const menu=[['HOME','Overview'],['DASHBOARD','Dashboard'],['PRODUCTION','Production'],['MIS','MIS Reports'],['WB','Weighbridge'],
      ['HSD','HSD'],['DRILL','Drilling'],['MECHANICAL','Mechanical'],['MASTERS','Masters'],['VOLVO','VOLVO / GPS'],['USERS','Users']];
    const granted={HOME:true,DASHBOARD:modules.includes('DASHBOARD'),PRODUCTION:modules.includes('PRODUCTION'),
      MIS:modules.includes('PRODUCTION'),WB:modules.includes('WB'),HSD:modules.includes('HSD'),
      DRILL:modules.includes('PRODUCTION'),MECHANICAL:management||modules.includes('MECHANICAL'),
      MASTERS:modules.includes('MASTERS'),VOLVO:management||modules.includes('DASHBOARD'),USERS:management};
    const nav=document.getElementById('nav');nav.hidden=false;
    nav.innerHTML=menu.filter(x=>granted[x[0]]).map(x=>'<button id="nav_'+x[0]+'" onclick="tiomGoNav('+"'"+x[0]+"'"+')">'+E(x[1])+'</button>').join('');
  };
  document.documentElement.classList.add('tiom-management-ui');
})();