/* TIOM Despatch: standalone Production sub-tab; does not change WB. */
(function(){
'use strict';
const $=id=>document.getElementById(id);
const v=id=>$(id)?.value||'';
const h=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const f=(n,d=3)=>Number(n||0).toLocaleString('en-IN',{minimumFractionDigits:d,maximumFractionDigits:d});
const base=window.renderProduction, oldTab=window.tiomProdTab;
let tab='dashboard',last={},page=1,search='';
async function api(path,body){
  const options={credentials:'same-origin',headers:{'X-NMTPL-Request':'webapp'}};
  if(body!==undefined){options.method='POST';options.body=body;if(typeof body==='string')options.headers['Content-Type']='application/json';}
  const r=await fetch('/api/tiom/despatch/'+path,options);
  if(!r.ok){let data={};try{data=await r.json()}catch(_){};throw Error(data.detail||('HTTP '+r.status));}
  return r.json();
}
const dates=()=>new URLSearchParams({from_date:v('dd_from'),to_date:v('dd_to')}).toString();
function say(s,error=false){if($('dd_notice')){$('dd_notice').textContent=s;$('dd_notice').style.color=error?'#b42318':'#187463';}}
window.renderProduction=function(){
  const reopen=sessionStorage.getItem('TIOM_DESPATCH_TAB')==='YES';
  base();
  const nav=document.querySelector('.tiom-prod-tabs');
  if(nav&&!$('tp_despatch')){
    const b=document.createElement('button');b.id='tp_despatch';b.textContent='Despatch Report';
    b.onclick=()=>window.tiomProdTab('DESPATCH');nav.appendChild(b);
  }
  if(reopen)window.tiomProdTab('DESPATCH');
};
window.tiomProdTab=function(name){
  if(name!=='DESPATCH'){sessionStorage.removeItem('TIOM_DESPATCH_TAB');return oldTab(name);}
  sessionStorage.setItem('TIOM_DESPATCH_TAB','YES');
  document.querySelectorAll('.tiom-prod-tabs button').forEach(b=>b.classList.remove('active'));
  $('tp_despatch')?.classList.add('active');
  const today=S.boot.today||'2026-10-26';
  $('tiom_prod_body').innerHTML='<div class="dd-root"><div class="dd-header"><div><h2>Despatch Dashboard</h2><p>External E-Pass dispatch / transporter / permit data</p></div>'+
   '<label>From <input type="date" id="dd_from" value="'+h(today.slice(0,7)+'-01')+'"></label>'+
   '<label>To <input type="date" id="dd_to" value="'+h(today)+'"></label><button class="btn primary small" onclick="tiomDDPanel()">Apply</button></div>'+
   '<div id="dd_notice" role="status"></div><nav class="dd-tabs">'+
   [['dashboard','Dashboard'],['trips','Trips & Cancellations'],['imports','Mail & Image Imports'],['reports','Five Reports'],['senders','Sender Settings']].map(p=>
   '<button data-tab="'+p[0]+'" onclick="tiomDDPanel(\''+p[0]+'\')">'+p[1]+'</button>').join('')+
   '</nav><div id="dd_body">Loading…</div></div>';
  window.tiomDDPanel('dashboard');
};
const bars=(title,rows)=>'<section class="dd-box"><b>'+h(title)+'</b>'+((rows||[]).slice(0,10).map(x=>
  '<div class="dd-bar"><span title="'+h(x.name)+'">'+h(x.name)+'</span><i><em style="width:'+Math.max(2,Math.min(100,+x.tonnes*100/Math.max(...rows.map(a=>+a.tonnes),1)))+'%"></em></i><strong>'+f(x.tonnes)+' MT</strong></div>'
).join('')||'<p>No records for period</p>')+'</section>';
window.tiomDDPanel=async function(which){
  tab=which||tab;
  document.querySelectorAll('.dd-tabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));
  $('dd_body').innerHTML='<div class="loading">Loading…</div>';
  try {
    if(tab==='dashboard'){
      const data=await api('dashboard?'+dates()),total=data.totals;last.dashboard=data;
      const max=Math.max(...data.daily.map(x=>+x.tonnes),1);
      $('dd_body').innerHTML='<div class="dd-kpis">'+[['Active trips',f(total.trips,0)],['Dispatch MT',f(total.tonnes)],['Cancelled trips',f(total.cancelled,0)],['Images pending',f(total.imagesReview,0)]]
       .map(x=>'<div><span>'+x[0]+'</span><strong>'+x[1]+'</strong></div>').join('')+'</div>'+
       '<section class="dd-box"><b>Daily dispatch trend</b><div class="dd-trend">'+data.daily.map(x=>
       '<div title="'+h(x.date)+' · '+f(x.tonnes)+' MT · '+x.trips+' trips"><i style="height:'+Math.max(2,(+x.tonnes/max*100))+'%"></i><small>'+h(x.date.slice(8))+'</small></div>').join('')+'</div></section>'+
       '<div class="dd-grid">'+bars('Destination',data.destination)+bars('Material / Grade',data.material)+bars('Transporter',data.transporter)+bars('Buyer',data.buyer)+'</div>';
    } else if(tab==='trips'){
      const data=await api('trips?'+dates()+'&page='+page+'&show_cancelled=true&q='+encodeURIComponent(search));last.trips=data;
      $('dd_body').innerHTML='<div class="dd-tools"><input id="dd_search" placeholder="E-Pass / vehicle / permit / transporter" value="'+h(search)+'"><button class="btn secondary small" onclick="tiomDDSearch()">Search</button>'+
       '<span>'+f(data.count,0)+' records · Page '+page+'</span><button class="btn secondary small" onclick="tiomDDPage(-1)">Previous</button><button class="btn secondary small" onclick="tiomDDPage(1)">Next</button></div>'+
       '<div class="dd-scroll"><table><thead><tr>'+['Date','E-Pass','Permit','Vehicle','Transporter','Destination','Grade','Net MT','Status','Edit'].map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+
       data.rows.map((x,i)=>'<tr><td>'+h(x.report_date)+'</td><td>'+h(x.epass_no)+'</td><td>'+h(x.permit_no)+'</td><td>'+h(x.vehicle_no)+'</td><td>'+h(x.transporter)+'</td><td>'+h(x.destination)+'</td><td>'+h(x.material_grade)+'</td><td>'+f(x.net_mt)+'</td><td>'+h(x.status)+'</td><td><button class="btn secondary tiny" onclick="tiomDDEdit('+i+')">Edit</button></td></tr>').join('')+'</tbody></table></div><div id="dd_editor"></div>';
    } else if(tab==='imports'){
      const imgs=await api('images');
      $('dd_body').innerHTML='<div class="dd-grid"><section class="dd-box"><b>Upload E-Pass data</b><p>Trip Summary Excel, or October historical CSV. Existing trips are not duplicated.</p>'+
       '<input id="dd_importfile" type="file" accept=".xlsx,.csv"><button class="btn primary small" onclick="tiomDDImport()">Import</button><button class="btn secondary small" onclick="tiomDDMail()">Sync Approved Gmail Now</button>'+
       '<hr><b>AMNS daily image</b><label>Report date <input type="date" id="dd_imgdate" value="'+h(v('dd_to'))+'"></label>'+
       '<input id="dd_imgfile" type="file" accept="image/jpeg,image/png,image/webp">'+
       '<button class="btn secondary small" onclick="tiomDDImage()">Upload for review</button><p>Images are retained; their figures require confirmation before use in reports.</p></section>'+
       '<section class="dd-box"><b>Images pending verification</b>'+
       (imgs.map(x=>'<div class="dd-image"><a target="_blank" href="/api/tiom/despatch/image/'+encodeURIComponent(x.id)+'">'+h(x.filename)+'</a><small>'+h(x.report_date||'Date pending')+' · '+h(x.review_status)+'</small><button class="btn secondary tiny" onclick="tiomDDReview(\''+h(x.id)+'\')">Verify permit</button></div>').join('')||'No images uploaded yet')+'</section></div><div id="dd_editor"></div>';
    } else if(tab==='reports'){
      $('dd_body').innerHTML='<section class="dd-box"><b>Download report</b><p>Date range above applies to all five reports.</p>'+
       [['trip','Trip Summary'],['transporter','Transporter Wise'],['material','Material Wise'],['destination','Destination Wise'],['despatch','Captive / Non-captive Despatch']].map(x=>
       '<div class="dd-report"><strong>'+x[1]+'</strong><button class="btn primary small" onclick="tiomDDExport(\''+x[0]+'\')">Download Excel</button></div>').join('')+'</section>';
    } else {
      const users=await api('senders');last.senders=users;
      $('dd_body').innerHTML='<section class="dd-box"><b>Authorized dispatch mail senders</b><p>Only management can change this list; WB sender rules are separate.</p>'+
       '<div class="dd-scroll"><table><thead><tr><th>Sender</th><th>Email</th><th>Status</th><th>Action</th></tr></thead><tbody>'+
       users.map((x,i)=>'<tr><td>'+h(x.name)+'</td><td>'+h(x.email)+'</td><td>'+(x.active?'Enabled':'Disabled')+'</td><td><button class="btn secondary tiny" onclick="tiomDDToggle('+i+')">'+(x.active?'Disable':'Enable')+'</button></td></tr>').join('')+'</tbody></table></div>'+
       '<div class="dd-tools"><input id="dd_newname" placeholder="New sender name"><input id="dd_newemail" placeholder="new@example.com" type="email"><button class="btn primary small" onclick="tiomDDAddSender()">Add sender</button></div></section>';
    }
  } catch(e){$('dd_body').innerHTML='<div class="panel bad">'+h(e.message)+'</div>';}
};
window.tiomDDSearch=()=>{search=v('dd_search');page=1;window.tiomDDPanel('trips');};
window.tiomDDPage=delta=>{page=Math.max(1,page+delta);window.tiomDDPanel('trips');};
window.tiomDDExport=type=>window.location.assign('/api/tiom/despatch/export/'+encodeURIComponent(type)+'?'+dates());
window.tiomDDMail=async()=>{
  say('Checking MIS Gmail mailbox…');
  try{const d=await api('mail-sync',JSON.stringify({}));say('Mailbox '+d.mailbox+': '+d.messagesScanned+' scanned, '+d.tripsInserted+' trips, '+d.imagesSaved+' images imported.');}
  catch(e){say(e.message,true);}
};
window.tiomDDImport=async()=>{
  const file=$('dd_importfile')?.files?.[0];if(!file)return say('Choose an import file',true);
  const fd=new FormData();fd.append('file',file);
  try{const r=await api('upload',fd);say(r.ok?'Imported '+r.inserted+' trips; '+r.skippedExisting+' existing; '+r.conflictCount+' conflicts.':'Import rejected: '+r.errorCount+' invalid rows.',!r.ok);}
  catch(e){say(e.message,true);}
};
window.tiomDDImage=async()=>{
  const file=$('dd_imgfile')?.files?.[0];if(!file)return say('Choose the AMNS image',true);
  const fd=new FormData();fd.append('file',file);fd.append('report_date',v('dd_imgdate'));
  try{const r=await api('image',fd);say('Image saved for verification: '+r.id);window.tiomDDPanel('imports');}
  catch(e){say(e.message,true);}
};
window.tiomDDEdit=i=>{
  const x=last.trips?.rows?.[i];if(!x)return;
  $('dd_editor').innerHTML='<section class="dd-box"><b>Edit / Cancel '+h(x.epass_no)+'</b><div class="dd-tools">'+
    '<label>Status <select id="dd_status"><option>ACTIVE</option><option>CANCELLED</option></select></label>'+
    '<label>Tare MT <input id="dd_tare" type="number" step="0.001" value="'+h(x.tare_mt)+'"></label>'+
    '<label>Gross MT <input id="dd_gross" type="number" step="0.001" value="'+h(x.gross_mt)+'"></label>'+
    '<label>Net MT <input id="dd_net" type="number" step="0.001" value="'+h(x.net_mt)+'"></label>'+
    '<label>Reason <input id="dd_reason" placeholder="Reason is mandatory" maxlength="500"></label>'+
    '<button class="btn primary small" onclick="tiomDDSave('+i+')">Save change</button></div></section>';
  $('dd_status').value=x.status;$('dd_editor').scrollIntoView({block:'nearest'});
};
window.tiomDDSave=async i=>{
  const x=last.trips?.rows?.[i];if(!x||v('dd_reason').trim().length<5)return say('Provide a reason (at least 5 characters)',true);
  try{await api('trip/'+encodeURIComponent(x.epass_no)+'/edit',JSON.stringify({
    status:v('dd_status'),tare_mt:v('dd_tare'),gross_mt:v('dd_gross'),net_mt:v('dd_net'),reason:v('dd_reason')}));
    say('Trip updated; audit recorded.');window.tiomDDPanel('trips');
  }catch(e){say(e.message,true);}
};
window.tiomDDToggle=async i=>{
  const x=last.senders?.[i];if(!x)return;
  try{await api('senders',JSON.stringify({email:x.email,name:x.name,active:!x.active}));window.tiomDDPanel('senders');}
  catch(e){say(e.message,true);}
};
window.tiomDDAddSender=async()=>{
  try{await api('senders',JSON.stringify({email:v('dd_newemail'),name:v('dd_newname'),active:true}));window.tiomDDPanel('senders');}
  catch(e){say(e.message,true);}
};
window.tiomDDReview=doc=>{
  $('dd_editor').innerHTML='<section class="dd-box"><b>Verified permit from AMNS image</b><div class="dd-tools">'+
  [['rdate','Date','date'],['permit','Permit','text'],['buyer','Buyer','text'],['dest','Destination','text'],['mat','Material','text'],
   ['grade','Grade %','text'],['qty','Permit MT','number'],['trips','Reported trips','number'],['tonnes','Reported MT','number'],['balance','Balance MT','number']]
   .map(x=>'<label>'+x[1]+' <input id="dd_'+x[0]+'" type="'+x[2]+'" '+(x[0]==='rdate'?'value="'+h(v('dd_to'))+'"':'')+'></label>').join('')+
   '<button class="btn primary small" onclick="tiomDDSaveReview(\''+h(doc)+'\')">Save verified permit</button></div><p>Enter values exactly as checked on the original image; invalid grades above 100% are rejected.</p></section>';
};
window.tiomDDSaveReview=async doc=>{
  const body={report_date:v('dd_rdate'),permit_no:v('dd_permit'),buyer:v('dd_buyer'),destination:v('dd_dest'),
    material:v('dd_mat'),grade_percent:v('dd_grade'),permit_qty:v('dd_qty')||null,
    reported_trips:v('dd_trips')?Number(v('dd_trips')):null,reported_mt:v('dd_tonnes')||null,
    balance_mt:v('dd_balance')||null,document_id:doc};
  try{await api('permit-review',JSON.stringify(body));say('Verified AMNS permit recorded');$('dd_editor').innerHTML='';}
  catch(e){say(e.message,true);}
};
})();