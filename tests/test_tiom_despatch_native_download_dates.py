"""Regression for date validation in the native Five Reports download links.

The UI may *display* 07-11-2026, while input[type=date].value is
2026-11-07. Check the actual browser-side callback to catch accidental
double escaping in a JS regex literal.
"""
from pathlib import Path
import re
import shutil
import subprocess

import pytest


def test_all_five_native_downloads_accept_real_html_date_values():
    js=(Path(__file__).parents[1]/"app"/"static"/"tiom_despatch.js").read_text("utf-8")
    match=re.search(
        r"window\.tiomDDNativeLink=\(anchor,type\)=>\{[\s\S]*?\n\};",
        js,
    )
    assert match, "Native download handler not found"
    node=shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed in this environment")

    code=r"""
const assert = require('node:assert/strict');
const window = {};
const values = {dd_to: '2026-11-07', dd_reportbasis: 'month'};
const v = (id) => values[id] || '';
const notices = [];
const say = (message, error) => notices.push({message, error});
const last = {mappingIssues: {items: []}};
""" + match.group(0) + r"""
for (const type of ['trip','transporter','material','destination','despatch']) {
  for (const date of ['2026-11-06','2026-11-07']) {
    values.dd_to = date;
    const anchor = {href: '#'};
    assert.equal(window.tiomDDNativeLink(anchor, type), true, type + ' ' + date);
    const url = new URL(anchor.href, 'https://example.test');
    assert.equal(url.pathname, '/api/tiom/despatch/export/' + type);
    assert.equal(url.searchParams.get('to_date'), date);
    assert.equal(url.searchParams.get('from_date'), '2026-11-01');
  }
}
values.dd_to = '2026-11-07';
values.dd_reportbasis = 'daily';
const daily = {href: '#'};
assert.equal(window.tiomDDNativeLink(daily, 'trip'), true);
assert.equal(new URL(daily.href, 'https://example.test').searchParams.get('from_date'),
             '2026-11-07');
values.dd_to = '07-11-2026'; // screen display format is not HTML input value
assert.equal(window.tiomDDNativeLink({href: '#'}, 'trip'), false);
values.dd_to = '';
assert.equal(window.tiomDDNativeLink({href: '#'}, 'trip'), false);
values.dd_to = '2026-11-07';
last.mappingIssues.tripFields = {reportDate: '2026-11-07', trips: 0};
last.mappingIssues.latestImportedDate = '2026-11-06';
assert.equal(window.tiomDDNativeLink({href: '#'}, 'trip'), false);
assert.match(notices.at(-1).message, /2026-11-06/);
values.dd_to = '2026-11-06';
last.mappingIssues.items = [{permitNo: 'UNVERIFIED'}];
assert.equal(window.tiomDDNativeLink({href: '#'}, 'despatch'), false);
assert.equal(window.tiomDDNativeLink({href: '#'}, 'trip'), true);
"""
    result=subprocess.run([node,"-e",code],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+"\n"+result.stderr
