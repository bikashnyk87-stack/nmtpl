/* WB analytics and full export use confirmed WB ledger only. No writes. */
(function(){
  const E=x=>esc(x??'');
  const number=(x,d=1)=>x==null?'—':Number(x).toLocaleString('en-IN',{maximumFractionDigits:d,minimumFractionDigits:d});
  const old=window.renderWb;
  window.renderWb=function(){
    old();
    const panel=document.createElement('section');panel.id='wb_full_report';panel.className='panel wb-full-report';
    panel.innerHTML='<div class="wb-full-title"><b>WB Full Data — Report & Download</b><span>Selected dates · Latest confirmed WB batch per shift</span></div>'+
    '<div class="wb-full-filter">'+
    '<label>From<input id="wbfull_from" type="date"></label><label>To<input id="wbfull_to" type="date"></label>'+
    '<label>Shift<select id="wbfull_shift"><option value="ALL">All shifts</option>'+opt(S.boot.masters.shifts,x=>x,x=>x)+'</select></label>'+
    '<label>Status<select id="wbfull_status"><option value="ALL">All statuses</option><option value="VALID">Valid</option><option value="REVIEW">Review</option></select></label>'+
    '<label>Material<input id="wbfull_material" placeholder="All materials"></label>'+
    '<label>Source<input id="wbfull_source" placeholder="All sources"></label>'+
    '<label>Destination<input id="wbfull_destination" placeholder="All destinations"></label>'+
    '<label>Vehicle<input id="wbfull_vehicle" placeholder="All vehicles"></label>'+
    '<button class="btn secondary small" onclick="tiomWbFullLoad()">Apply</button>'+
    '<button class="btn primary small" onclick="tiomWbDownload()">Download Full XLSX</button></div>'+
    '<div id="wbfull_result" class="loading">Loading WB report…</div>';
    const target=document.getElementById('wb_monitor');
    if(target)target.before(panel);else document.getElementById('app').appendChild(panel);
    const d=new Date(S.boot.today+'T12:00:00');d.setDate(d.getDate()-6);
    document.getElementById('wbfull_to').value=S.boot.today;
    document.getElementById('wbfull_from').value=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
    tiomWbFullLoad();
  };
  function filters(){const val=id=>document.getElementById(id)?.value||'';return {
    fromDate:val('wbfull_from'),toDate:val('wbfull_to'),shift:val('wbfull_shift')||'ALL',
    status:val('wbfull_status')||'ALL',materialFilter:val('wbfull_material'),
    sourceFilter:val('wbfull_source'),destinationFilter:val('wbfull_destination'),
    vehicleFilter:val('wbfull_vehicle')};}
  function statsCard(a,b,note){return '<div class="wb-full-kpi"><small>'+E(a)+'</small><strong>'+E(b)+'</strong><span>'+E(note)+'</span></div>'}
  function dataTable(headers,rows){return '<div class="wb-full-scroll"><table><thead><tr>'+
    headers.map(x=>'<th>'+E(x)+'</th>').join('')+'</tr></thead><tbody>'+
    (rows.length?rows.map(row=>'<tr>'+row.map(x=>'<td>'+E(x)+'</td>').join('')+'</tr>').join(''):
      '<tr><td colspan="'+headers.length+'">No matching WB records</td></tr>')+'</tbody></table></div>'}
  window.tiomWbFullLoad=function(){
    const requested=filters();
    appRun(d=>{
      if(S.screen!=='WB'||!document.getElementById('wbfull_result'))return;
      const k=d.kpis||{};
      const cards=[
        statsCard('Valid WB',number(k.validMovements,0),'Movements'),
        statsCard('WB Net Weight',number(k.validTonnes,2)+' t','Valid only'),
        statsCard('Review',number(k.reviewMovements,0),'Needs attention'),
        statsCard('Vehicles',number(k.uniqueVehicles,0),'Distinct'),
        statsCard('Avg Payload',number(k.avgPayloadMt,2)+' t','Valid only'),
        statsCard('Batches',number(k.batches,0),'Latest confirmed')
      ].join('');
      const material=dataTable(['Material','Trips','Net tonnes'],(d.materials||[]).map(x=>[x.material,number(x.trips,0),number(x.tonnes,2)]));
      const movement=dataTable(['Date','Shift','WB No.','Vehicle','Material','Source','Destination','MT','Status'],
        (d.rows||[]).map(x=>[x.date,x.shift,x.movementNo,x.vehicle,x.material,x.source,x.destination,number(x.netMt,2),x.status]));
      document.getElementById('wbfull_result').innerHTML='<div class="wb-full-kpis">'+cards+'</div>'+
      '<div class="wb-full-panels"><section><h3>Material-wise WB</h3>'+material+'</section>'+
      '<section><h3>WB movements · '+number(d.previewCount,0)+' / '+number(d.filteredRecords,0)+' records</h3>'+movement+
      '<p class="note">Download Full XLSX exports all matching records, including tare, gross and net weight, time, master ID, batch and exceptions.</p></section></div>';
    },e=>{const el=document.getElementById('wbfull_result');if(el)el.innerHTML='<div class="bad">'+E(e.message)+'</div>'}).getTiomWbHistory(requested);
  };
  window.tiomWbDownload=function(){
    const qs=new URLSearchParams(filters());
    window.location.assign('/api/web/wb/full-export?'+qs.toString());
  };
})();