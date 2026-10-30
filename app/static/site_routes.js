/* KOCP movement masters: separate Coal/OB routes, combined unique physical locations. */
(function(){
  const routeData={COAL:[],OB:[]};
  function h(v){return esc(v==null?'':v)}
  function table(kind,rows){
    const body=rows.map(function(r){
      return '<tr><td>'+h(r.group)+'</td><td>'+h(r.source||'—')+'</td><td>'+h(r.destination)+
        '</td><td>'+h(r.category)+'</td><td>'+h(r.distanceRange)+'</td><td>'+
        (r.active?'Active':'Inactive')+'</td><td><button type="button" class="btn outline mini" onclick="editKocpRoute(\''+
        r.routeId+'\')">Edit</button></td></tr>';
    }).join('');
    return '<div class="table-wrap"><table class="data-table"><thead><tr><th>Group</th><th>From</th><th>To</th><th>Category</th>'+
      '<th>Distance range</th><th>Status</th><th></th></tr></thead><tbody>'+
      (body||'<tr><td colspan="7">No routes imported yet.</td></tr>')+'</tbody></table></div>';
  }
  function one(kind){
    const data=routeData[kind]||[];
    const title=kind==='COAL'?'Coal Route & Distance Master':'OB Route & Distance Master';
    const body='<p class="helper">Upload '+kind+' Excel. Routes stay separate; physical locations are collected automatically.</p>'+
      '<div class="form-grid cols-3"><div class="field"><span>'+kind+' Excel file</span>'+
      '<input id="kocpFile'+kind+'" type="file" accept=".xlsx"></div><div class="form-actions">'+
      '<button type="button" class="btn outline" onclick="location.href=\'/api/sites/KOCP/routes/'+kind+'/template.xlsx\'">Sample Excel</button>'+
      '<button type="button" class="btn primary" onclick="previewKocpRoute(\''+kind+'\')">Validate / Preview</button></div></div>'+
      '<div id="kocpPreview'+kind+'" style="margin-top:9px"></div>'+
      '<div id="kocpEdit'+kind+'" style="margin-top:9px"></div>'+table(kind,data);
    return panel(title,body,data.length+' routes');
  }
  async function renderKocpRoutePanels(){
    try{
      const results=await Promise.all([
        api('/api/sites/KOCP/routes?kind=COAL'),
        api('/api/sites/KOCP/routes?kind=OB'),
        api('/api/sites/KOCP/routes/locations')
      ]);
      routeData.COAL=results[0];routeData.OB=results[1];
      const locations=results[2];
      const body=locations.map(function(x){
        return '<tr><td>'+h(x.name)+'</td><td>'+h((x.usedIn||[]).join(', ')||'Existing location')+
          '</td><td>'+(x.active?'Active':'Inactive')+'</td></tr>';
      }).join('');
      return one('COAL')+one('OB')+panel('Location Master — Automatic',
        '<div class="callout good">Combined unique physical locations from Coal and OB. No separate upload is required.</div>'+
        '<div class="table-wrap"><table class="data-table"><thead><tr><th>Location</th><th>Used by</th><th>Status</th></tr></thead><tbody>'+
        (body||'<tr><td colspan="3">Locations appear after confirming Coal/OB routes.</td></tr>')+
        '</tbody></table></div>',locations.length+' unique locations');
    }catch(e){
      return panel('Coal / OB route masters','<div class="callout warn">Unable to load routes: '+h(e.message)+'</div>');
    }
  }
  async function previewKocpRoute(kind){
    try{
      const file=document.getElementById('kocpFile'+kind)?.files?.[0];
      if(!file)throw new Error('Choose the '+kind+' Excel file.');
      const fd=new FormData();fd.append('file',file);
      const r=await api('/api/sites/KOCP/routes/'+kind+'/preview',{method:'POST',body:fd});
      const errors=(r.errors||[]).map(e=>'<div>Row '+e.row+': '+h((e.errors||[]).join('; '))+'</div>').join('');
      document.getElementById('kocpPreview'+kind).innerHTML=
        '<div class="callout '+(r.errorRows?'warn':'good')+'"><b>'+kind+': '+r.totalRows+
        ' rows · '+r.errorRows+' errors</b>'+(errors||'<div>Validated. No master changed yet.</div>')+'</div>'+
        (r.ok&&r.errorRows===0?'<div style="margin-top:7px"><button class="btn primary" type="button" onclick="confirmKocpRoute(\''+
         r.batchId+'\')">Confirm '+kind+' Import</button></div>':'');
    }catch(e){toast(e.message,'bad')}
  }
  async function confirmKocpRoute(batch){
    try{
      const r=await api('/api/sites/KOCP/routes/imports/'+batch+'/confirm',{method:'POST'});
      toast('Imported '+r.rows+' routes: '+r.created+' new, '+r.updated+' updated');
      await render();
    }catch(e){toast(e.message,'bad')}
  }
  function editKocpRoute(id){
    const kind=['COAL','OB'].find(k=>routeData[k].some(r=>r.routeId===id));
    if(!kind)return;
    const r=routeData[kind].find(x=>x.routeId===id),target=document.getElementById('kocpEdit'+kind);
    target.innerHTML='<div class="callout"><b>Edit '+kind+': '+h(r.group)+' → '+h(r.destination)+'</b>'+
      '<div class="form-grid cols-3"><div class="field"><span>Category</span>'+
      '<input id="kocpEditCategory" value="'+h(r.category)+'"></div>'+
      '<div class="field"><span>Distance range</span><input id="kocpEditDistance" value="'+h(r.distanceRange)+'"></div>'+
      '<div class="field"><span>Status</span><select id="kocpEditActive">'+
      '<option value="true" '+(r.active?'selected':'')+'>Active</option>'+
      '<option value="false" '+(!r.active?'selected':'')+'>Inactive</option></select></div></div>'+
      '<div class="form-actions"><button type="button" class="btn primary" onclick="saveKocpRoute(\''+id+'\')">Save route</button>'+
      '<button type="button" class="btn outline" onclick="document.getElementById(\'kocpEdit'+kind+'\').innerHTML=\'\'">Cancel</button></div></div>';
    target.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
  async function saveKocpRoute(id){
    try{
      const body={category:document.getElementById('kocpEditCategory').value.trim(),
                  distanceRange:document.getElementById('kocpEditDistance').value.trim(),
                  active:document.getElementById('kocpEditActive').value==='true'};
      await api('/api/sites/KOCP/routes/'+id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      toast('Route updated');await render();
    }catch(e){toast(e.message,'bad')}
  }
  Object.assign(window,{renderKocpRoutePanels,previewKocpRoute,confirmKocpRoute,editKocpRoute,saveKocpRoute});
})();
