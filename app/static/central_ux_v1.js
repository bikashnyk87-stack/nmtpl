
(function(){
try{centralNav.splice(0,centralNav.length,
['MANAGEMENT',[['EXECUTIVE','DB','Dashboard'],['SITES','ST','Sites'],['PRODUCTION','PR','Production'],['FLEET','FL','Fleet'],['FUEL','HS','Fuel / HSD'],['WORKFORCE','WF','People']]],
['CONTROL',[['QUALITY','DQ','Data Issues'],['REPORTS','RP','Reports'],['MAPS','MP','Maps & Satellite'],['MASTERS','MS','Masters'],['ACCESS','AC','Users'],['AUDIT','AU','Approvals & History'],['SYSTEM','SY','System']]]);}catch(e){}
ctx=function(){return `<div class="context-strip"><span class="context-pill live">Central</span><span class="context-pill">TIOM · SOCP · KOCP</span><span class="context-pill">Role-based access</span><span class="context-pill">PostgreSQL live data</span></div>`};
state.managementDate=state.managementDate||new Date().toISOString().slice(0,10);
if(typeof loadCentralOverview==='function'){loadCentralOverview=async function(){try{state.centralOverview=await api(`/api/site-ops/central/overview?operating_date=${encodeURIComponent(state.managementDate)}`);const by=Object.fromEntries((state.centralOverview.sites||[]).map(x=>[x.siteId,x]));state.siteDash={...state.siteDash,...by}}catch(e){console.warn(e)}}}
function bar(){return `<div class="management-date"><label>Management Date<input id="managementDate" type="date" value="${esc(state.managementDate)}"></label><button class="btn primary" onclick="applyManagementDate()">Apply</button><small>Top KPIs use this operating date.</small></div>`}
if(typeof renderExecutive12==='function'){const o=renderExecutive12;renderExecutive12=function(){return bar()+o()}}else{const o=renderExecutive;renderExecutive=function(){return bar()+o()}}
window.applyManagementDate=async function(){const e=document.getElementById('managementDate');if(e)state.managementDate=e.value;if(typeof loadCentralOverview==='function')await loadCentralOverview();await render();toast('Management date updated')};
const f=document.getElementById('sideVersion');if(f)f.textContent='v1.0 RC1';
setTimeout(()=>{try{setNav();render()}catch(e){console.warn(e)}},250);
})();
