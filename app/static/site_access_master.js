/* Site-scoped User Access inside Masters (TIOM / KOCP / SOCP).
   Writes only through the admin access API; other sites' grants are preserved.
*/
(function(){
'use strict';
const $access=id=>document.getElementById(id);
const safe=v=>esc(String(v==null?'':v));
const custom={
  DESPATCH_EVIDENCE:['Upload Despatch evidence','CREATE'],
  DESPATCH_IMPORT:['Import Despatch files / sync Gmail','CREATE'],
  DESPATCH_REVIEW:['Review Despatch permits / mappings','EDIT']
};
const actions=['VIEW','CREATE','EDIT','APPROVE','EXPORT'];
let users=[],current='',visible=new URLSearchParams(location.search).get('access')==='1';
let loading=false;
function isManager(){return state.bootstrap?.user?.isManagement===true}
function modules(){
  const site=state.bootstrap?.sites?.find(s=>s.siteId===siteId);
  return [...new Set([...(site?.modules||[]),...(siteId==='TIOM'?Object.keys(custom):[])])];
}
function permsFor(module){
  return custom[module]?[custom[module][1]]:actions;
}
function mount(){
  const root=$access('workspace');
  if(!root||state.module!=='MASTERS'||!isManager()||$access('siteAccessMaster'))return;
  const html='<section id="siteAccessMaster">'+panel(
    'User & Permission Master · '+safe(siteId),
    '<div class="toolbar"><p class="helper">Manage site assignment, View, Create, Edit, Approve and Export per user. Other mine sites retain their existing rights.</p>'+
    '<button type="button" class="btn outline" onclick="toggleSiteAccessMaster()">'
    +(visible?'Close permissions':'Manage user permissions')+'</button></div>'+
    '<div id="smAccessBody" '+(visible?'':'hidden')+'><p>Loading user permissions…</p></div>',
    'Super Admin only · No password changes or cross-site permission changes'
  )+'</section>';
  root.insertAdjacentHTML('afterbegin',html);
  if(visible)loadSiteAccessMaster();
}
function toggle(){
  const body=$access('smAccessBody');
  if(!body)return;
  visible=!visible;body.hidden=!visible;
  const btn=$access('siteAccessMaster')?.querySelector('button');
  if(btn)btn.textContent=visible?'Close permissions':'Manage user permissions';
  if(visible)loadSiteAccessMaster();
}
async function loadSiteAccessMaster(){
  const body=$access('smAccessBody');
  if(!body||!isManager()||!visible||loading)return;
  loading=true;
  try{
    users=await api('/api/sites/admin/access');
    const options=users.map(u=>'<option value="'+safe(u.loginId)+'" '+(current===u.loginId?'selected':'')+'>'+
       safe(u.name)+' · '+safe(u.loginId)+(u.admin?' · Admin':'')+'</option>').join('');
    if(!users.some(u=>u.loginId===current))current=users[0]?.loginId||'';
    body.innerHTML='<div class="toolbar"><label>Account <select id="smAccessAccount" onchange="chooseSiteAccessUser(this.value)">'+options+'</select></label>'+
       '<button type="button" class="btn outline" onclick="loadSiteAccessMaster()">Refresh</button>'+
       '<button type="button" class="btn outline" onclick="location.href=\'/central-control\'">Create user in Central Control</button></div>'+
       '<div id="smAccessEditor"></div>';
    if($access('smAccessAccount'))$access('smAccessAccount').value=current;
    renderEditor();
  }catch(e){body.innerHTML='<div class="callout bad">'+safe(e.message)+'</div>'}
  finally{loading=false}
}
function chooseUser(id){current=id;renderEditor()}
function renderEditor(){
  const target=$access('smAccessEditor');
  if(!target)return;
  const u=users.find(x=>x.loginId===current);
  if(!u){target.innerHTML='<p>No user selected.</p>';return}
  const granted=new Set(u.permissions||[]);
  const rows=modules().map(m=>{
    const chips=permsFor(m).map(action=>{
      const key=siteId+'.'+m+'.'+action;
      return '<label class="perm-chip"><input type="checkbox" class="smSiteGrant" data-grant="'+safe(key)+'" '+(granted.has(key)?'checked':'')+'> '+safe(custom[m]?'Allow':action)+'</label>';
    }).join('');
    const label=custom[m]?.[0]||m.replaceAll('_',' ');
    return '<div class="perm-row"><b>'+safe(label)+'</b><div>'+chips+'</div></div>';
  }).join('');
  const assigned=(u.sites||[]).includes(siteId);
  target.innerHTML='<div class="callout"><b>'+safe(u.name)+'</b> · '+safe(u.loginId)+
    (u.admin?' · Management account (administrator bypasses module restrictions)':' · Standard user')+'</div>'+
    '<label class="check-field"><input id="smSiteAssigned" type="checkbox" '+(assigned?'checked':'')+
    '> Assign user to '+safe(siteId)+'</label>'+
    '<div class="toolbar"><button type="button" class="btn outline" onclick="siteAccessPreset(\'VIEWER\')">View only</button>'+
    '<button type="button" class="btn outline" onclick="siteAccessPreset(\'OPERATOR\')">Entry & view</button>'+
    '<button type="button" class="btn outline" onclick="siteAccessPreset(\'CLEAR\')">Clear permissions</button></div>'+
    '<div class="permission-grid">'+rows+'</div>'+
    '<div class="form-actions"><button type="button" class="btn primary" id="smAccessSave" onclick="saveSiteAccessMaster()">Save '+safe(siteId)+' permissions</button></div>'+
    '<p class="helper">Only this site will be changed. Existing grants in other sites remain intact. Sensitive operations still require management or explicit approval.</p>';
}
function preset(mode){
  const controls=[...document.querySelectorAll('#smAccessEditor .smSiteGrant')];
  controls.forEach(c=>{
    const parts=c.dataset.grant.split('.');
    const module=parts[1],action=parts[2];
    if(mode==='CLEAR')c.checked=false;
    if(mode==='VIEWER')c.checked=action==='VIEW'&&!custom[module];
    if(mode==='OPERATOR')c.checked=(['VIEW','CREATE'].includes(action)&&!custom[module])
      || (module==='DESPATCH_EVIDENCE'&&action==='CREATE');
  });
}
async function saveSiteAccessMaster(){
  const save=$access('smAccessSave'),selected=current;
  const enabled=!!$access('smSiteAssigned')?.checked;
  const previous=users.find(u=>u.loginId===selected);
  if(!previous||!save)return;
  if(!enabled&&(previous.sites||[]).includes(siteId)&&!confirm('Remove '+selected+' from '+siteId+'? This will revoke all '+siteId+' module permissions.'))return;
  save.disabled=true;
  try{
    // Fetch again before merging, so another site administrator's latest
    // KOCP/SOCP/TIOM grants are not overwritten by a stale browser snapshot.
    const latest=(await api('/api/sites/admin/access')).find(u=>u.loginId===selected);
    if(!latest)throw new Error('The account no longer exists. Refresh.');
    const sites=new Set(latest.sites||[]);
    if(enabled)sites.add(siteId);else sites.delete(siteId);
    const permissions=(latest.permissions||[]).filter(x=>!x.startsWith(siteId+'.'));
    if(enabled){
      const chosen=[...document.querySelectorAll('#smAccessEditor .smSiteGrant:checked')].map(e=>e.dataset.grant);
      permissions.push(...chosen);
    }
    const defaultSite=!enabled&&latest.defaultSite===siteId?
      ([...sites][0]||null):(latest.defaultSite||(enabled?siteId:null));
    const body={sites:[...sites],permissions:[...new Set(permissions)],defaultSite};
    await api('/api/sites/admin/access/'+encodeURIComponent(selected),{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)
    });
    toast(siteId+' permissions saved for '+selected);
    await loadSiteAccessMaster();
  }catch(e){toast(e.message,'bad')}
  finally{if($access('smAccessSave'))$access('smAccessSave').disabled=false}
}
const root=$access('workspace');
if(root){
  new MutationObserver(mount).observe(root,{childList:true});
  mount();
}
Object.assign(window,{
  toggleSiteAccessMaster:toggle,
  loadSiteAccessMaster,
  chooseSiteAccessUser:chooseUser,
  siteAccessPreset:preset,
  saveSiteAccessMaster
});
})();