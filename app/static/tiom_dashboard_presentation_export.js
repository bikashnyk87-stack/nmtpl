/* TIOM dashboard: presentation-ready, filter-preserving report export.
 * A self-contained HTML document makes the saved report available offline,
 * and the same document is used for A4 landscape print / Save as PDF.
 */
(function () {
  'use strict';
  function escapeText(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function cleanNumber(value, places) {
    if (value === null || value === undefined || value === '') return 'Not available';
    var n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString('en-IN', {minimumFractionDigits: places, maximumFractionDigits: places}) : 'Not available';
  }
  function amount(value, places, suffix) {
    var number = cleanNumber(value, places === undefined ? 1 : places);
    return number === 'Not available' ? number : number + (suffix || '');
  }
  function rows(value) { return Array.isArray(value) ? value : []; }
  function field(value) { return '<td>' + escapeText(value) + '</td>'; }
  function table(headings, data, empty) {
    if (!data.length) return '<p class="empty">' + escapeText(empty || 'No recorded rows for this period.') + '</p>';
    return '<div class="scroll"><table><thead><tr>' + headings.map(function (h) { return '<th>' + escapeText(h) + '</th>'; }).join('') +
      '</tr></thead><tbody>' + data.map(function (row) {
        return '<tr>' + row.map(field).join('') + '</tr>';
      }).join('') + '</tbody></table></div>';
  }
  function section(title, note, body, cls) {
    return '<section class="panel ' + (cls || '') + '"><div class="panel-head"><h2>' + escapeText(title) + '</h2><span>' +
      escapeText(note || '') + '</span></div>' + body + '</section>';
  }
  function card(label, value, subtitle, tone) {
    return '<div class="kpi ' + (tone || '') + '"><span>' + escapeText(label) +
      '</span><strong>' + escapeText(value) + '</strong><small>' + escapeText(subtitle) + '</small></div>';
  }
  function barChart(items, metric) {
    if (!items.length) return '<p class="empty">No materials recorded for this period.</p>';
    var largest = Math.max.apply(null, [1].concat(items.map(function (x) { return Math.max(0, Number(x[metric] || 0)); })));
    return '<div class="bars">' + items.slice(0, 14).map(function (x) {
      var value = Math.max(0, Number(x[metric] || 0)), width = Math.max(0, Math.min(100, value / largest * 100));
      return '<div class="bar-row"><span>' + escapeText(x.label || x.name || 'Material') + '</span>' +
        '<div class="bar-track"><i style="width:' + width.toFixed(2) + '%"></i></div>' +
        '<b>' + escapeText(amount(x[metric], 1, ' t')) + '</b></div>';
    }).join('') + '</div>';
  }
  function bodyHtml(d) {
    var k = d.kpis || {}, p = d.production || {}, production = rows(d.productionMaterials);
    var allocationPending = !!p.allocationPending || p.finalProductionMt == null;
    var dateText = String(d.fromDate || '—') + (d.fromDate !== d.toDate ? ' to ' + String(d.toDate || '—') : '');
    var filters = [
      (d.shift && d.shift !== 'ALL') ? 'Shift ' + d.shift : 'All shifts',
      d.materialFilter ? 'Material: ' + d.materialFilter : '',
      d.sourceFilter ? 'Source: ' + d.sourceFilter : '',
      d.destinationFilter ? 'Destination: ' + d.destinationFilter : '',
      d.vehicleFilter ? 'Vehicle: ' + d.vehicleFilter : ''
    ].filter(Boolean);
    var html = '<div class="report-head"><div class="logo">N<span>MTPL</span></div><div class="identity">' +
      '<b>THAKURANI IRON ORE MINES</b><span>MINING OPERATIONS  /  MANAGEMENT INFORMATION REPORT</span></div>' +
      '<div class="report-type">OPERATIONS<br>REPORT</div></div>' +
      '<div class="report-title"><div><div class="eyebrow">OPERATING PERFORMANCE</div>' +
      '<h1>Production & Operations Dashboard</h1><p>' + escapeText(dateText) + ' &nbsp;•&nbsp; ' + escapeText(filters.join('  •  ')) +
      '</p></div><div class="date-chip">TIOM<br><b>' + escapeText(d.toDate || '—') + '</b></div></div>';
    html += '<div class="kpis">' + [
      card('Fresh ROM', amount(p.romInputMt, 2, ' t'), 'Mine-origin material', 'teal'),
      card('Screen direct output', amount(p.screenDirectMt, 2, ' t'), 'Direct screened output', ''),
      card('Crusher gross output', amount(p.crusherGrossOutputMt, 2, ' t'), 'Before blend allocation', ''),
      card('Final fresh production', allocationPending ? 'Allocation pending' : amount(p.finalProductionMt, 2, ' t'), 'Do not include old stock', allocationPending ? 'amber' : 'teal'),
      card('OB removed', amount(k.obRemovedMt == null ? k.wasteTonnes : k.obRemovedMt, 2, ' t'), 'Confirmed WB / validated MIS basis', ''),
      card('Old stock / RH', amount(p.oldStockExcludedMt == null ? k.oldStockExcludedMt : p.oldStockExcludedMt, 2, ' t'), 'Excluded from fresh production', 'amber'),
      card('WB movements', amount(k.wbTrips, 0), 'Valid weighbridge records', ''),
      card('WB movement tonnes', amount(k.wbTonnes, 2, ' t'), 'Movement audit, NOT final production', '')
    ].join('') + '</div>';
    html += section('Production & recovery KPIs',
      'Every value comes from the selected dashboard period; recovery is withheld if allocation is pending',
      '<div class="report-kpi-grid">' + [
        card('Screen fines', amount(p.screenFinesMt, 2, ' t'), '0–10 fines from screen'),
        card('Screen 5–18', amount(p.screen518Mt, 2, ' t'), 'Screen product 5–18'),
        card('Plant feed', amount(p.plantFeedMt, 2, ' t'), 'Recorded physical feed'),
        card('Total crusher feed', amount(p.crusherFeedMt, 2, ' t'), 'Fresh + old-stock blend'),
        card('Fresh crusher output', allocationPending ? 'Pending allocation' : amount(p.crusherFreshOutputMt, 2, ' t'), 'Net of allocated blend', allocationPending ? 'amber' : ''),
        card('Final recovery', allocationPending ? 'Pending allocation' : amount(p.finalRecoveryPct, 2, '%'), 'Fresh final / fresh ROM', allocationPending ? 'amber' : 'teal'),
        card('Crusher recovery', amount(p.crusherRecoveryPct, 2, '%'), 'Gross output / crusher feed'),
        card('Process / timing balance', allocationPending ? 'Pending allocation' : amount(p.balanceMt, 2, ' t'), 'Fresh ROM less final fresh output', allocationPending ? 'amber' : '')
      ].join('') + '</div>', 'kpi-section');
    var flow = [
      ['Fresh ROM', p.romInputMt],
      ['Plant feed', p.plantFeedMt],
      ['Screen direct', p.screenDirectMt],
      ['Crusher gross', p.crusherGrossOutputMt],
      ['Final fresh', allocationPending ? null : p.finalProductionMt]
    ];
    html += section('Production flow & allocation',
      'ROM is the production base; old-stock rehandling is excluded',
      '<div class="flow">' + flow.map(function (x, i) {
        return (i ? '<span class="arrow">→</span>' : '') +
          '<div class="flow-node"><span>' + escapeText(x[0]) + '</span><b>' +
          escapeText(x[1] == null ? 'Pending' : amount(x[1], 1, ' t')) + '</b></div>';
      }).join('') + '</div>' +
      (allocationPending ? '<p class="notice">Fresh crusher-output allocation is pending supporting feed / blend evidence. Final fresh production is not estimated.</p>' : ''));
    var prodData = production.map(function (x) {
      return [x.label || '—', amount(x.trips, 0), amount(x.tonnes, 2, ' t'),
        amount(x.monthTonnes, 2, ' t'), x.excluded ? 'EXCLUDED' : amount(x.pct, 1, '%')];
    });
    html += section('Material production',
      'Process-based quantities • do not add successive stages to obtain production',
      table(['Material / stage', 'Trips', 'Period tonnes', 'Month tonnes', '% of fresh ROM'], prodData, 'No process-material records in selected period.'));
    var plants = rows(d.plantPerformance);
    html += section('Plant feed vs output',
      'Feed, recycle and output are separate physical movements',
      table(['Plant', 'Fresh feed (t)', 'Recycle (t)', 'Old stock (t)', 'Gross throughput (t)', 'Final / fresh (t)', 'Running hours', 'TPH'],
        plants.map(function (x) { return [
          x.plant || '—', amount(x.freshFeedMt == null ? x.feedMt : x.freshFeedMt, 1),
          amount(x.recycleMt, 1), amount(x.blendFeedMt, 1),
          amount(x.grossThroughputMt == null ? x.feedMt : x.grossThroughputMt, 1),
          x.outputMt == null ? 'Allocation pending' : amount(x.outputMt, 1),
          amount(x.runningHours, 2), amount(x.tph, 2)
        ];}), 'No plant feed/output records in selected period.'), 'page-break');
    html += '<div class="two-col">' +
      section('Material mix — WB movement audit', 'These are weighed movements, not the finished-product total',
        barChart(rows(d.materials), 'tonnes')) +
      section('Shift comparison', 'A / B / C • selected reporting period',
        table(['Shift', 'Trips', 'Tonnes', 'HSD issued'], rows(d.shiftComparison).map(function (x) {
          return [x.shift || '—', amount(x.trips, 0), amount(x.tonnes, 1), amount(x.fuel, 1, ' L')];
        }), 'No shift comparison recorded.')) + '</div>';
    html += section('Haulage productivity & WB reconciliation',
      'Recorded haulage performance • missing lead distance is never estimated',
      '<div class="report-kpi-grid">' + [
        card('Trips / active hour', amount(k.tripsPerHour, 2), 'Haulage pace'),
        card('Average lead', amount(k.haulAvgLeadKm, 3, ' km'), 'Quantity-weighted lead'),
        card('Trip-km / hour', amount(k.tripKmPerHour, 2), 'Trips × lead / active hr'),
        card('Tonne-km / hour', amount(k.tonKmPerHour, 2), 'Tonnes × lead / active hr'),
        card('Average payload', amount(k.avgPayload, 2, ' t'), 'WB movement payload'),
        card('Avg cycle time', amount(k.avgCycleTime, 1, ' min'), 'Movement start to unload'),
        card('Avg loading time', amount(k.avgLoadingTime, 1, ' min'), 'Movement start to loaded'),
        card('Match rate', amount(k.matchRate, 1, '%'), 'WB movement reconciliation'),
        card('WB ↔ MIS linked', amount(k.misWbLinkedTrips, 0), 'Linked WB/MIS records'),
        card('WB ↔ Field matched', amount(k.matched, 0), 'Exact field matches'),
        card('WB unmatched', amount(k.wbUnmatched, 0), 'Unlinked WB movements', Number(k.wbUnmatched) > 0 ? 'amber' : ''),
        card('Lead missing', amount(k.haulLeadMissingTrips, 0), 'Route distance needs review', Number(k.haulLeadMissingTrips) > 0 ? 'amber' : '')
      ].join('') + '</div>', 'kpi-section');
    var hsdPerFinalTon = p.finalProductionMt != null && !allocationPending &&
      Number(p.finalProductionMt) > 0 && k.hsdLitres != null
      ? Number(k.hsdLitres) / Number(p.finalProductionMt) : null;
    html += section('HSD & equipment utilization',
      'HSD issued is not actual consumption • productivity counts are activity indicators',
      '<div class="report-kpi-grid">' + [
        card('HSD issued', amount(k.hsdLitres, 1, ' L'), 'Issued from HSD ledger'),
        card('HSD / trip', amount(k.fuelPerTrip, 2, ' L'), 'Reported issued-fuel indicator'),
        card('HSD / fresh final t', amount(hsdPerFinalTon, 3, ' L/t'), 'Requires verified fresh output'),
        card('Working equipment', amount(k.workingEquipment, 0), 'Equipment-shift count'),
        card('Running loaders', amount(k.runningLoaders, 0), 'Recorded activity'),
        card('Running excavators', amount(k.runningExcavators, 0), 'Recorded activity'),
        card('Running tippers', amount(k.runningTippers, 0), 'Recorded activity'),
        card('Equipment utilization', amount(k.equipmentUtilization, 1, '%'), 'Activity-based utilization')
      ].join('') + '</div>', 'kpi-section');
    var b = d.breakdowns || {}, monthly = d.monthly || {};
    html += '<div class="two-col">' +
      section('Drilling performance', 'Drill and compressor HMR where recorded',
        '<div class="small-kpis">' + [
          card('Drilled holes', amount(k.drillHoles, 0), 'Period total'),
          card('Drill meterage', amount(k.drillMeterage, 2, ' m'), 'ROM / OB / BHJ / BHQ'),
          card('Drill metres / hour', amount(k.drillMeterPerHour, 2, ' m/h'), 'HMR-based drilling rate'),
          card('Drill HSD issued', amount(k.drillHsdLitres, 1, ' L'), 'Drill + compressor'),
          card('Drill breakdown', amount(k.drillBreakdownHours, 1, ' h'), 'Recorded breakdown hours'),
          card('Drill HSD / metre', amount(k.drillMeterage > 0 && k.drillHsdLitres != null ? Number(k.drillHsdLitres) / Number(k.drillMeterage) : null, 3, ' L/m'), 'Issued HSD / measured meterage')
        ].join('') + '</div>') +
      section('Maintenance & month-to-date', 'MTD is a separate monthly view through the selected report date',
        '<div class="small-kpis">' + [
          card('Open breakdowns', amount(b.activeEvents, 0), 'Recorded mechanical events'),
          card('Period downtime', amount(b.periodDowntimeHours, 1, ' h'), 'Shift overlap hours'),
          card('Month fresh output', amount(monthly.actual, 2, ' t'), 'Month-to-date final output'),
          card('Avg daily fresh', amount(monthly.avgDaily, 2, ' t'), 'Month-to-date daily average'),
          card('Best day output', amount(monthly.bestTonnes, 2, ' t'), monthly.bestDay || 'No recorded day'),
          card('Worst day output', amount(monthly.worstTonnes, 2, ' t'), monthly.worstDay || 'No recorded day')
        ].join('') + '</div>') +
      '</div>';
    var routeRows = rows(d.routes).slice(0, 20).map(function (x) {
      return [x.source || 'Unmapped', x.destination || 'Unmapped', amount(x.trips, 0),
        amount(x.tonnes, 2), amount(x.avgPayload, 2)];
    });
    html += section('WB routes & locations', 'Source → destination mapping must be complete before using route KPIs',
      table(['Source', 'Destination', 'WB trips', 'Movement t', 'Avg payload t'], routeRows, 'No route records in selected period.'));
    var issues = [];
    if (allocationPending) issues.push('Final fresh production is pending verified crusher feed and blend allocation.');
    if (Number(k.wbUnmatched || 0) > 0) issues.push(amount(k.wbUnmatched, 0) + ' weighbridge movements have no matched field record.');
    if (Number(k.haulLeadMissingTrips || 0) > 0) issues.push(amount(k.haulLeadMissingTrips, 0) + ' haulage trips do not have a resolved lead distance.');
    if (rows(d.routes).some(function (x) {return /unmapped/i.test(String(x.source || '') + ' ' + String(x.destination || ''));}))
      issues.push('Unmapped source / destination appears in WB routes; do not infer a real route or lead.');
    html += section('Management notes & data coverage', 'Evidence limitations are retained in printed exports',
      '<div class="notes">' + (issues.length ? '<ul>' + issues.map(function (x) {
        return '<li>' + escapeText(x) + '</li>';
      }).join('') + '</ul>' : '<p>No exceptions flagged by these report checks.</p>') +
      '<p><b>Definitions:</b> WB tonnage is a movement/reconciliation total, not final fresh production. Fresh ROM, material outputs, rehandling, fuel and productivity must not be added together. A displayed 0 means zero recorded by the source for the selected filters, not proof that no field activity occurred.</p>' +
      '<p><b>Source:</b> current TIOM dashboard data, with the same period, shift and dimension filters shown in the report header.</p></div>');
    html += '<footer><span>NMTPL | Thakurani Iron Ore Mines</span><span>Controlled operational report  •  ' + escapeText(dateText) + '</span></footer>';
    return html;
  }
  function reportDocument(d) {
    var css = [
      '@page{size:A4 landscape;margin:12mm 12mm 15mm}',
      '*{box-sizing:border-box}body{margin:0;background:#edf4f7;color:#123245;font:12px/1.45 Arial,Helvetica,sans-serif}',
      '.sheet{width:min(1120px,100%);margin:22px auto;background:white;box-shadow:0 12px 38px #143e532b;padding:24px 28px}',
      '.report-head{display:flex;align-items:center;gap:16px;background:#09273b;color:#fff;margin:-24px -28px 22px;padding:18px 28px}',
      '.logo{background:#00a3a1;color:#fff;font-weight:800;font-size:22px;padding:7px 12px;letter-spacing:1px;border-radius:6px}.logo span{font-size:17px}',
      '.identity{display:flex;flex-direction:column;gap:2px}.identity b{font-size:14px;letter-spacing:1px}.identity span{font-size:10px;color:#bdd8e5;letter-spacing:1.2px}',
      '.report-type{margin-left:auto;text-align:right;font-size:11px;font-weight:800;letter-spacing:1.1px;color:#d1ebf3}',
      '.report-title{display:flex;justify-content:space-between;align-items:center;gap:15px;border-bottom:3px solid #00a3a1;padding-bottom:15px;margin-bottom:18px}',
      '.eyebrow{font-size:10px;letter-spacing:1.4px;font-weight:800;color:#07878e}.report-title h1{margin:4px 0 6px;font-size:24px;line-height:1.15;color:#09273b}.report-title p{margin:0;color:#5c7484}',
      '.date-chip{border:1px solid #c7dce6;background:#e6f5f6;border-radius:8px;min-width:135px;text-align:center;padding:11px;color:#037b80;font-weight:700}.date-chip b{display:block;color:#103548;font-size:15px;margin-top:3px}',
      '.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:18px}',
      '.kpi{min-width:0;border:1px solid #d2e2e9;border-left:4px solid #2077a9;background:#f5f9fb;border-radius:7px;padding:10px 12px;display:flex;flex-direction:column;gap:5px;break-inside:avoid}',
      '.kpi.teal{border-left-color:#008986;background:#effbfa}.kpi.amber{border-left-color:#d19b2b;background:#fff9ec}',
      '.kpi span{font-size:10px;font-weight:800;letter-spacing:.4px;color:#567287;text-transform:uppercase}',
      '.kpi strong{font-size:19px;line-height:1.24;color:#09273b;overflow-wrap:anywhere}.kpi small{font-size:10px;color:#5e7789}',
      '.panel{border:1px solid #d2e0e7;border-radius:7px;margin:13px 0;background:white;overflow:hidden;break-inside:avoid}',
      '.panel-head{padding:10px 12px;background:#e9f3f7;border-bottom:1px solid #d2e0e7;display:flex;justify-content:space-between;gap:15px;align-items:center}',
      '.panel-head h2{margin:0;color:#10384e;font-size:14px}.panel-head span{font-size:10px;color:#627a8b;text-align:right}',
      'table{width:100%;border-collapse:collapse;font-size:10.5px}th{background:#f4f8fa;color:#173b50;font-weight:800;text-align:left}th,td{padding:7px 9px;border:1px solid #d9e6ec;vertical-align:top;overflow-wrap:anywhere}tbody tr:nth-child(even){background:#f8fbfc}',
      '.scroll{width:100%;overflow-x:auto}.empty{padding:15px;color:#6b8190}.flow{display:flex;align-items:stretch;gap:6px;padding:13px}.flow-node{background:#eaf7f6;border:1px solid #c4e1de;border-radius:6px;padding:11px 8px;flex:1;min-width:0;text-align:center}.flow-node span{display:block;font-size:10px;font-weight:700;color:#54717c}.flow-node b{display:block;margin-top:5px;font-size:15px;color:#094353}.arrow{align-self:center;font-size:18px;color:#008e98}',
      '.notice{margin:0 13px 12px;padding:10px;background:#fff4da;color:#845e17;border-left:3px solid #e5af48}',
      '.two-col{display:grid;grid-template-columns:1fr 1fr;gap:13px;align-items:start}.two-col .panel{margin:0}',
      '.bars{padding:13px}.bar-row{display:grid;grid-template-columns:1.5fr 1fr auto;align-items:center;gap:9px;padding:4px 0;font-size:9.5px}.bar-row span{overflow-wrap:anywhere}.bar-row b{white-space:nowrap;font-size:10px}.bar-track{height:9px;background:#e4eef3;border-radius:10px;overflow:hidden}.bar-track i{display:block;background:#00918e;height:100%;border-radius:10px}',
      '.report-kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;padding:12px}.report-kpi-grid .kpi strong{font-size:16px}.report-kpi-grid .kpi{padding:9px 10px}.kpi-section{break-inside:auto}',
      '.small-kpis{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;padding:12px}.small-kpis .kpi{padding:9px}.small-kpis .kpi strong{font-size:16px}',
      '.notes{padding:9px 16px;font-size:11px;color:#496679}.notes ul{margin:6px 0 10px;padding-left:18px}.notes li{margin-bottom:5px}.notes p{margin:7px 0}',
      'footer{display:flex;justify-content:space-between;font-size:9px;color:#6b8391;border-top:1px solid #d7e4ea;padding-top:12px;margin-top:18px}',
      '@media print{body{background:white;-webkit-print-color-adjust:exact;print-color-adjust:exact}.sheet{width:auto;margin:0;padding:0;box-shadow:none}.report-head{margin:0 0 16px;padding:13px 17px}.kpi,.two-col{break-inside:avoid}.panel{break-inside:auto}.panel-head{break-after:avoid}.report-kpi-grid{gap:6px;padding:8px}.report-kpi-grid .kpi strong{font-size:13px}.report-kpi-grid .kpi{padding:6px 8px}table{font-size:9.4px}th,td{padding:5px 7px}.kpis{gap:7px}.kpi{padding:8px}.kpi strong{font-size:15px}.panel-head h2{font-size:12px}.flow-node b{font-size:12px}.page-break{break-before:page}.report-title h1{font-size:20px}}',
      '@media(max-width:740px){.sheet{margin:0;padding:13px}.report-head{margin:-13px -13px 15px;padding:12px}.report-type{display:none}.kpis,.report-kpi-grid{grid-template-columns:repeat(2,1fr)}.two-col{grid-template-columns:1fr}.flow{overflow-x:auto}.flow-node{min-width:125px}.report-title h1{font-size:19px}}'
    ].join('\n');
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
      '<title>TIOM Management Report ' + escapeText(d.fromDate || '') + ' - ' + escapeText(d.toDate || '') + '</title><style>' +
      css + '</style></head><body><main class="sheet">' + bodyHtml(d) + '</main></body></html>';
  }
  window.dashboardPresentationReport = function (mode) {
    var d = typeof S !== 'undefined' && S.dashboard;
    if (!d || !d.kpis) {
      if (typeof toast === 'function') toast('Load the dashboard before exporting the report.');
      return;
    }
    var content = reportDocument(d);
    if (mode === 'print') {
      var w = window.open('', '_blank');
      if (!w) {
        if (typeof toast === 'function') toast('Allow pop-ups to open the printable report.');
        return;
      }
      w.onload = function () { w.focus(); w.print(); };
      w.document.open(); w.document.write(content); w.document.close();
      return;
    }
    var name = 'TIOM_Management_Report_' + (d.fromDate || 'date') + '_' + (d.toDate || 'date') + '.html';
    var blob = new Blob([content], {type:'text/html;charset=utf-8'}), url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = name; a.style.display = 'none';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
  };
  // PDF printing uses the same layout as the downloadable report, not the interactive application chrome.
  window.dashboardPrint = function () { window.dashboardPresentationReport('print'); };
})();