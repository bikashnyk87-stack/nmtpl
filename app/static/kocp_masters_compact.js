/* KOCP: one master per tab, small searchable grids, audited imports. */
(function(){
  const priorRender=render;
  const vm={tab:'COAL',materialKind:'COAL',search:'',page:1,size:12,summary:{},
    routes:{COAL:[],OB:[]},materials:{COAL:[],OB:[]},locations:[],existingMaterials:[],
    records:[],importOpen:false,formOpen:false,edit:null,preview:null,loading:false};
  const tabs=[
    ['COAL','Coal routes'],['OB','OB routes'],['MATERIALS','Materials'],
    ['EQUIPMENT','Equipment / Vehicles'],['EMPLOYEE','Employees'],
    ['LOCATIONS','Locations'],['HISTORY','Import history']
  ];
  const x=v=>esc(v===undefined||v===null?'':String(v));
  const st=v=>'<span class="kcm-status'+(v?'':' off')+'">'+(v?'Active':'Inactive')+'</span>';
  const action=(label,fn,cls)=>'<button type="button" class="kcm-btn '+(cls||'')+'" onclick="'+fn+'">'+label+'</button>';
  const typeKey=()=>vm.tab==='MATERIALS'?vm.materialKind:vm.tab==='LOCATIONS'?'LOCATION':vm.tab;
  const count=t=>t==='COAL'||t==='OB'?(vm.routes[t]||[]).length:t==='MATERIALS'?vm.summary.materials||0:
    t==='EMPLOYEE'?vm.summary.employees||0:t==='EQUIPMENT'?vm.summary.equipment||0:
    t==='LOCATIONS'?vm.locations.length:(vm.summary.imports||[]).length;
  const title=()=>tabs.find(t=>t[0]===vm.tab)?.[1]||'Master';
  function currentRows(){
    if(vm.tab==='COAL'||vm.tab==='OB')return vm.routes[vm.tab]||[];
    if(vm.tab==='MATERIALS')return vm.existingMaterials.filter(r=>{
      const unit=String(r.defaultUnit||'').toUpperCase();
      return vm.materialKind==='OB'?['CUM','M3','M³'].includes(unit):unit==='MT';
    });
    if(vm.tab==='LOCATIONS')return vm.locations;
    if(vm.tab==='HISTORY')return vm.summary.imports||[];
    return vm.records||[];
  }
  function filtered(){
    const q=vm.search.trim().toLowerCase();
    return currentRows().filter(row=>!q||Object.values(row).some(v=>String(v??'').toLowerCase().includes(q)));
  }
  function columnHeaders(){
    switch(vm.tab){
      case'COAL':return ['Movement group','Destination','Category','Distance range','Status',''];
      case'OB':return ['Category / Group','From','To','Distance range','Status',''];
      case'MATERIALS':return ['Material','Code','Group','Unit','Status',''];
      case'EMPLOYEE':return ['Employee ID','Name','Role','Department','Mobile','Status',''];
      case'EQUIPMENT':return ['ID','Type','Category','Make / Model','Ownership','Status',''];
      case'LOCATIONS':return ['Location','Code','Used in','Status'];
      default:return ['Batch','Type','Rows','Errors','Status','Uploaded by'];
    }
  }
  function cells(r){
    if(vm.tab==='COAL')return ['<b class="kcm-primary">'+x(r.group)+'</b>',x(r.destination),x(r.category),
      '<span class="kcm-pill">'+x(r.distanceRange)+'</span>',st(r.active),
      action('Edit','kcmEdit(\''+r.routeId+'\')','small')];
    if(vm.tab==='OB')return ['<b class="kcm-primary">'+x(r.group)+'</b>',x(r.source),x(r.destination),
      '<span class="kcm-pill">'+x(r.distanceRange)+'</span>',st(r.active),
      action('Edit','kcmEdit(\''+r.routeId+'\')','small')];
    if(vm.tab==='MATERIALS')return ['<b class="kcm-primary">'+x(r.name)+'</b>',x(r.code),
      x(r.materialGroup||'—'),x(r.defaultUnit),st(r.active),
      action('Edit','kcmEdit(\''+x(r.recordId)+'\')','small')];
    if(vm.tab==='EMPLOYEE')return ['<b class="kcm-primary">'+x(r.employeeId)+'</b>',x(r.name),x(r.role),
      x(r.department||'—'),x(r.mobile||'—'),st(r.active),action('Edit','kcmEdit(\''+x(r.employeeId)+'\')','small')];
    if(vm.tab==='EQUIPMENT'){
      const wrong=/L150H/i.test(r.makeModel||'')&&/TRIPPER|TIPPER|DUMPER/i.test(r.type||'');
      return ['<b class="kcm-primary">'+x(r.machineId)+'</b>',
        x(r.type)+(wrong?'<span class="kcm-tag missing">L150H is a loader · correct type</span>':''),
        x(r.group),x(r.makeModel||'—'),x(r.ownership||'—'),st(r.active),
        action(wrong?'Correct Type':'Edit','kcmEdit(\''+x(r.machineId)+'\')','small')];
    }
    if(vm.tab==='LOCATIONS')return ['<b class="kcm-primary">'+x(r.name)+'</b>',x(r.code),
      (r.usedIn||[]).map(v=>'<span class="kcm-tag">'+x(v)+'</span>').join(' ')||'Not assigned',st(r.active)];
    return ['<span class="kcm-primary">'+x(r.batchId)+'</span>',x(r.masterType),x(r.totalRows),
      x(r.errorRows),'<span class="kcm-tag">'+x(r.status)+'</span>',x(r.uploadedBy)];
  }
  function updateGrid(){
    const root=document.getElementById('kcmGrid');
    if(!root)return;
    const rows=filtered(),pages=Math.max(1,Math.ceil(rows.length/vm.size));vm.page=Math.max(1,Math.min(pages,vm.page));
    const visible=rows.slice((vm.page-1)*vm.size,vm.page*vm.size);
    const heads=columnHeaders();
    root.innerHTML='<div class="kcm-table-wrap"><table class="kcm-table"><thead><tr>'+
      heads.map(z=>'<th>'+x(z)+'</th>').join('')+'</tr></thead><tbody>'+
      (visible.map(r=>'<tr>'+cells(r).map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')||
        '<tr><td colspan="'+heads.length+'" class="kcm-empty">No matching records</td></tr>')+
      '</tbody></table></div><div class="kcm-footer"><span>'+
      (rows.length?String((vm.page-1)*vm.size+1)+'–'+String(Math.min(vm.page*vm.size,rows.length)):'0')+
      ' of '+rows.length+'</span>'+
      '<button type="button" class="kcm-btn small" '+(vm.page<=1?'disabled':'')+' onclick="kcmPage(-1)">Previous</button>'+
      '<button type="button" class="kcm-btn small" '+(vm.page>=pages?'disabled':'')+' onclick="kcmPage(1)">Next</button></div>';
  }
  function searchBar(){return '<input class="kcm-search" type="search" id="kcmSearchBox" placeholder="Search '+x(title()).toLowerCase()+
    '..." value="'+x(vm.search)+'" oninput="kcmSearch(this.value)">'}
  function toolbar(){
    const interactive=vm.tab!=='HISTORY';
    const materials=vm.tab==='MATERIALS';
    const importAction=interactive?action('Import Excel','kcmToggleImport()',''):'';
    const addAction=interactive?action('+ Add Single Entry','kcmToggleForm()',vm.formOpen?'':'primary'):'';
    const hint=vm.tab==='LOCATIONS'?'<span class="kcm-muted">Shared physical locations for Coal and OB routes</span>':'';
    const subTab=materials?'<div class="kcm-subtabs">'+
      ['COAL','OB'].map(k=>'<button type="button" class="'+(vm.materialKind===k?'active':'')+
      '" onclick="kcmKind(\''+k+'\')">'+k+' · '+vm.existingMaterials.filter(r=>
        k==='OB'?['CUM','M3','M³'].includes(String(r.defaultUnit||'').toUpperCase()):
        String(r.defaultUnit||'').toUpperCase()==='MT').length+' records</button>').join('')+
      '</div>':'';
    return subTab+'<div class="kcm-toolbar"><h2>'+x(title())+'</h2>'+hint+
      '<span class="kcm-spacer"></span>'+searchBar()+addAction+importAction+'</div>';
  }
  function sourceNote(){
    if(vm.tab==='MATERIALS')return '<div class="kcm-note">Saved Material Masters are shown below. Add one material or import Excel; existing codes cannot be overwritten through Add Single Entry.</div>';
    if(vm.tab==='COAL'||vm.tab==='OB')return '<div class="kcm-note">Add one route with its movement group, unloading point and distance. Existing physical locations are reused; Excel import is optional.</div>';
    if(vm.tab==='LOCATIONS')return '<div class="kcm-note">Add physical locations only once. Coal and OB movement routes share these locations.</div>';
    return '';
  }
  function importSection(){
    if(!vm.importOpen)return '';
    const k=typeKey(),route=k==='COAL'||k==='OB';
    const material=vm.tab==='MATERIALS';
    const path=material?'/api/sites/KOCP/material-types/'+k:
      route?'/api/sites/KOCP/routes/'+k:'/api/sites/KOCP/masters/'+k;
    const template=path+'/template.xlsx';
    return '<div class="kcm-import"><div class="kcm-import-row">'+
      '<input type="file" id="kcmUpload" accept=".xlsx">'+
      action('Validate / Preview','kcmPreview()','primary')+
      '<button type="button" class="kcm-btn" onclick="location.href=\''+template+'\'">Download sample Excel</button>'+
      action('Close','kcmToggleImport()','')+
      '</div><div id="kcmPreviewBox" class="kcm-preview"></div>'+
      '<div class="kcm-muted" style="margin-top:7px">No records are changed until you review and confirm.</div></div>';
  }
  function field(id,label,value,type,options){
    const val=value===undefined||value===null?'':value;
    let input='';
    if(type==='checkbox'){
      input='<label><input id="kcmF_'+id+'" type="checkbox" '+(val?'checked':'')+'> Active</label>';
    }else if(type==='location_suggest'){
      const list='kcmLocations_'+id;
      const choices=[...new Set(vm.locations.filter(loc=>loc.active).map(loc=>String(loc.name||'').trim()).filter(Boolean))];
      input='<input id="kcmF_'+id+'" type="text" list="'+list+'" value="'+x(val)+'">'+
        '<datalist id="'+list+'">'+choices.map(loc=>'<option value="'+x(loc)+'"></option>').join('')+'</datalist>';
    }else if(type==='route_suggest'){
      const list='kcmRouteOptions_'+id;
      const choices=[...new Set((vm.routes[vm.tab]||[]).filter(route=>route.active)
        .map(route=>String(route[id]||'').trim()).filter(Boolean))];
      input='<input id="kcmF_'+id+'" type="text" list="'+list+'" value="'+x(val)+'">'+
        '<datalist id="'+list+'">'+choices.map(value=>'<option value="'+x(value)+'"></option>').join('')+'</datalist>';
    }else if(type==='equipment_class'){
      // Suggestions are live Equipment Master types, not a built-in category list.
      const types=[...new Set((vm.records||[]).filter(e=>e.active&&e.type)
        .map(e=>String(e.type).trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
      input='<input id="kcmF_'+id+'" type="text" list="kcmExistingVehicleTypes" maxlength="80"'+
        ' placeholder="Type exactly as approved in Equipment Master" value="'+x(val)+'">'+
        '<datalist id="kcmExistingVehicleTypes">'+
        types.map(t=>'<option value="'+x(t)+'"></option>').join('')+'</datalist>';
    }else if(options){
      const choices=(String(val).trim()&&!options.includes(String(val)))?[String(val),...options]:options;
      input='<select id="kcmF_'+id+'" '+(id==='type'?'onchange="kcmSyncGroup()"':'')+'>'+
      choices.map(v=>'<option value="'+x(v)+'" '+(val===v?'selected':'')+'>'+x(v)+'</option>').join('')+'</select>';
    }else{
      input='<input id="kcmF_'+id+'" type="'+(type||'text')+'" '+(type==='number'?'step="any"':'')+
        ' value="'+x(val)+'">';
    }
    return '<label class="kcm-field"><span>'+x(label)+'</span>'+input+'</label>';
  }
  function form(){
    if(!vm.formOpen)return '';
    const r=vm.edit||{},route=vm.tab==='COAL'||vm.tab==='OB';
    let fields=[];
    if(route&&vm.edit)fields=[
      field('category','Movement category',r.category),
      field('distanceRange','Distance range',r.distanceRange),
      field('active','Status',r.active,'checkbox')
    ];
    else if(route)fields=[
      field('group','Movement group *','','route_suggest'),
      ...(vm.tab==='OB'?[field('source','From / source location *','','location_suggest')]:[]),
      field('destination','Destination / unloading point *','','location_suggest'),
      field('category','Movement category *','','route_suggest'),
      field('distanceRange','Distance range *'),
      field('locationType','Location type'),
      field('active','Active',true,'checkbox')
    ];
    else if(vm.tab==='MATERIALS')fields=[
      field('code','Material code *',r.code),
      field('name','Material name *',r.name),
      field('materialGroup','Material group',r.materialGroup),
      field('defaultUnit','Default unit *',r.defaultUnit||(vm.materialKind==='OB'?'CUM':'MT')),
      field('billableUnit','Billable unit',r.billableUnit||(vm.materialKind==='OB'?'CUM':'MT')),
      field('active','Active',r.active??true,'checkbox')
    ];
    else if(vm.tab==='LOCATIONS')fields=[
      field('code','Location code *'),
      field('name','Physical location name *'),
      field('locationType','Location type'),
      field('active','Active',true,'checkbox')
    ];
    else if(vm.tab==='EMPLOYEE')fields=[
      field('employeeId','Employee ID *',r.employeeId),
      field('name','Name *',r.name),
      field('role','Role *',r.role),
      field('department','Department',r.department),
      field('mobile','Mobile',r.mobile),
      field('effectiveFrom','Effective From',r.effectiveFrom?.slice(0,10),'date'),
      field('active','Active',r.active??true,'checkbox')
    ];
    else if(vm.tab==='EQUIPMENT')fields=[
      field('machineId','Machine ID *',r.machineId),
      field('type','Physical machine type / MCL vehicle class *',r.type||'','equipment_class'),
      field('group','Work group (COAL / OB / BOTH) *',r.group||''),
      field('makeModel','Make / Model',r.makeModel),
      field('vehicleNo','Registration',r.vehicleNo),
      field('doorNo','Door No',r.doorNo),
      field('ownership','Ownership class',r.ownership||'OWN','select',['OWN','NMTPL','HIRED','CONTRACTOR','THIRD PARTY','OTHER']),
      field('party','Party',r.party),
      field('bucketCum','Bucket CuM',r.bucketCum,'number'),
      field('ratedPayloadT','Payload T',r.ratedPayloadT,'number'),
      field('effectiveFrom','Effective From',r.effectiveFrom?.slice(0,10),'date'),
      field('active','Active',r.active??true,'checkbox')
    ];
    if(vm.tab==='MATERIALS'&&vm.edit){
      fields.unshift('<div class="kcm-note">Editing the selected material. Its code identifies linked production records; change descriptive fields here. Create a separate material with Add Single Entry if a new code is needed.</div>');
    }
    if(vm.tab==='EQUIPMENT'){
      fields.unshift('<div class="kcm-note"><b>Vehicle classes come from this Equipment Master.</b> For transport vehicles, enter the full approved type (for example, the manufacturer and tipper type) consistently. The MCL dropdown uses active KOCP vehicle types only. There are no built-in class options.</div>');
    }
    if(vm.tab==='EQUIPMENT'&&/L150H/i.test(r.makeModel||'')&&/TIPPER|TRIPPER|DUMPER/i.test(r.type||'')){
      fields.unshift('<div class="kcm-note"><strong>Type mismatch:</strong> Volvo L150H is a Loader, not a Tripper. Change Physical machine type to Loader, retain the Coal/OB work group, then save the master. Historical fuel entries are preserved.</div>');
    }
    return '<div class="kcm-form"><div class="kcm-formhead"><h3>'+x(vm.edit?'Edit '+title():'New '+title())+
      '</h3>'+action('Close','kcmToggleForm()','small')+'</div><div class="kcm-formgrid">'+fields.join('')+
      '</div><div class="kcm-actions">'+action('Cancel','kcmToggleForm()','')+
      action('Save changes','kcmSave()','primary')+'</div></div>';
  }
  function materialExisting(){return '';} // Grid above shows all actual saved materials.
  async function refreshData(){
    const calls=[
      api('/api/sites/KOCP/master-summary'),
      api('/api/sites/KOCP/routes?kind=COAL'),
      api('/api/sites/KOCP/routes?kind=OB'),
      api('/api/sites/KOCP/routes/locations'),
      api('/api/sites/KOCP/material-types'),
      api('/api/sites/KOCP/masters/MATERIAL/records?limit=1000')
    ];
    if(vm.tab==='EMPLOYEE'||vm.tab==='EQUIPMENT')
      calls.push(api('/api/sites/KOCP/masters/'+vm.tab+'/records?limit=1000'));
    const res=await Promise.all(calls);
    vm.summary=res[0]||{};vm.routes.COAL=res[1]||[];vm.routes.OB=res[2]||[];
    vm.locations=res[3]||[];vm.materials=res[4]||{COAL:[],OB:[]};vm.existingMaterials=res[5]||[];
    vm.records=res[6]||[];
  }
  async function renderCompact(){
    if(siteId!=='KOCP'||state.module!=='MASTERS')return priorRender();
    setNav();
    $('crumbTop').textContent='NMTPL / KOCP';$('crumbTitle').textContent='Master Management';
    try{await refreshData()}catch(e){
      $('workspace').innerHTML='<div class="kcm"><div class="kcm-card"><div class="kcm-note">Unable to load Masters: '+x(e.message)+'</div></div></div>';return;
    }
    const metrics=[
      ['Coal routes',count('COAL')],['OB routes',count('OB')],
      ['Shared locations',count('LOCATIONS')],['Employees',count('EMPLOYEE')],
      ['Equipment',count('EQUIPMENT')]
    ];
    const head='<div class="kcm-header"><div><h1 class="kcm-title">Master Management</h1>'+
      '<p class="kcm-sub">One master at a time · Bulk import and single editing · KOCP</p></div>'+
      action('Refresh','loadCurrentModule()','small')+'</div>';
    const m='<div class="kcm-metrics">'+metrics.map(k=>
      '<div class="kcm-metric"><small>'+x(k[0])+'</small><strong>'+x(k[1])+'</strong></div>').join('')+'</div>';
    const tabbar='<div class="kcm-tabs" role="tablist">'+tabs.map(t=>
      '<button type="button" class="kcm-tab" role="tab" aria-selected="'+(vm.tab===t[0])+
      '" onclick="kcmGo(\''+t[0]+'\')">'+x(t[1])+'<em>'+x(count(t[0]))+'</em></button>').join('')+'</div>';
    $('workspace').innerHTML='<div class="kcm">'+head+m+tabbar+
      '<div class="kcm-card">'+toolbar()+sourceNote()+form()+importSection()+
      '<div id="kcmGrid"></div>'+materialExisting()+'</div></div>';
    updateGrid();
  }
  function kcmGo(tab){vm.tab=tab;vm.search='';vm.page=1;vm.importOpen=false;vm.formOpen=false;vm.edit=null;vm.preview=null;render()}
  function kcmKind(kind){vm.materialKind=kind;vm.search='';vm.page=1;vm.importOpen=false;vm.preview=null;render()}
  function kcmSearch(v){vm.search=v;vm.page=1;updateGrid()}
  function kcmPage(n){vm.page+=n;updateGrid()}
  function kcmToggleImport(){vm.importOpen=!vm.importOpen;vm.formOpen=false;vm.preview=null;render()}
  function kcmToggleForm(){vm.formOpen=!vm.formOpen;vm.importOpen=false;vm.edit=null;render()}
  function kcmEdit(id){
    vm.edit=currentRows().find(r=>r.routeId===id||r.employeeId===id||r.machineId===id||r.recordId===id)||null;
    vm.formOpen=true;vm.importOpen=false;render();
  }
  function kcmSyncGroup(){
    // The group is the operating area (COAL/OB/BOTH), not the physical type.
    // Selecting Loader or Tipper must never rewrite a Coal group to LOADING.
    const t=$('kcmF_type'),m=$('kcmF_makeModel');
    if(!t||!m)return;
    const isLoader=/L150H/i.test(m.value);
    if(isLoader&&/TIPPER|TRIPPER|DUMPER/i.test(t.value))
      toast('L150H is a Volvo loader. Select Loader before saving the master.','bad');
  }
  async function kcmSave(){
    try{
      const body={},idFields=[...document.querySelectorAll('.kcm-form [id^=kcmF_]')];
      idFields.forEach(el=>body[el.id.replace('kcmF_','')]=el.type==='checkbox'?el.checked:el.value.trim()||null);
      if(vm.tab==='MATERIALS'&&vm.edit&&String(body.code||'').toUpperCase()!==String(vm.edit.code||'').toUpperCase())
        throw new Error('Material code cannot change on Edit. Use Add Single Entry for a new code.');
      if(vm.tab==='COAL'||vm.tab==='OB'){
        const url=vm.edit?'/api/sites/KOCP/routes/'+vm.edit.routeId:
          '/api/sites/KOCP/routes/'+vm.tab+'/records';
        await api(url,{method:'POST',
          headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      }else{
        const kind=vm.tab==='MATERIALS'?'MATERIAL':vm.tab==='LOCATIONS'?'LOCATION':vm.tab;
        body.createOnly=!vm.edit;
        await api('/api/sites/KOCP/masters/'+kind+'/records',{method:'POST',
          headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      }
      toast('Master saved successfully');vm.formOpen=false;vm.edit=null;await render();
    }catch(e){toast(e.message,'bad')}
  }
  async function kcmPreview(){
    try{
      const file=$('kcmUpload')?.files?.[0];if(!file)throw new Error('Choose an Excel file first.');
      const k=typeKey();
      let url=vm.tab==='MATERIALS'?'/api/sites/KOCP/material-types/'+k+'/preview':
        (vm.tab==='COAL'||vm.tab==='OB')?'/api/sites/KOCP/routes/'+k+'/preview':
        '/api/sites/KOCP/masters/'+k+'/preview';
      const fd=new FormData();fd.append('file',file);
      const r=await api(url,{method:'POST',body:fd});
      const error=(r.errors||[]).map(z=>'<div>Row '+x(z.row)+': '+x((z.errors||[]).join('; '))+'</div>').join('');
      const kinds=vm.tab==='MATERIALS'?' · '+x(r.materialTypeCount)+' distinct material types':'';
      const warnings=vm.tab==='MATERIALS'&&r.routeUnmatchedRows?.length?
        '<p class="kcm-muted">No exact route match for source rows: '+x(r.routeUnmatchedRows.join(', '))+
        '. Original rows remain in the audit; routes are not overwritten.</p>':'';
      vm.preview={batchId:r.batchId,mode:vm.tab,kind:k};
      $('kcmPreviewBox').innerHTML='<div><strong>'+x(r.totalRows)+' source rows'+kinds+
        ' · '+x(r.errorRows)+' errors</strong></div>'+
        (error?'<div class="kcm-issues">'+error+'</div>':'<p class="kcm-status">Validation passed; nothing saved yet.</p>')+
        warnings+
        (r.errorRows===0&&r.ok?'<button type="button" class="kcm-btn primary" onclick="kcmConfirm()">Confirm import</button>':'');
    }catch(e){toast(e.message,'bad')}
  }
  async function kcmConfirm(){
    if(!vm.preview)return;
    try{
      const p=vm.preview;const url=p.mode==='MATERIALS'?
        '/api/sites/KOCP/material-types/imports/'+p.batchId+'/confirm':
        (p.mode==='COAL'||p.mode==='OB')?'/api/sites/KOCP/routes/imports/'+p.batchId+'/confirm':
        '/api/sites/KOCP/masters/imports/'+p.batchId+'/confirm';
      const r=await api(url,{method:'POST'});
      toast(p.mode==='MATERIALS'?
        (r.materialTypes+' material types reconciled from '+r.sourceRows+' rows; '+r.created+' added'):
        ('Import successful: '+(r.rows||r.totalRows||0)+' rows'));
      vm.importOpen=false;vm.preview=null;await render();
    }catch(e){toast(e.message,'bad')}
  }
  render=renderCompact;window.render=renderCompact;
  Object.assign(window,{kcmGo,kcmKind,kcmSearch,kcmPage,kcmToggleImport,kcmToggleForm,
    kcmEdit,kcmSyncGroup,kcmSave,kcmPreview,kcmConfirm});
})();
