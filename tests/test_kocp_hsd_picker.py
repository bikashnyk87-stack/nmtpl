"""KOCP equipment picker regressions found in field verification (31 Oct 2026).

Coal and OB production are distinct, but HSD covers every active KOCP asset.
An earlier UI request limit=40 silently hid 91 out of 131 HSD choices.
"""
from pathlib import Path

from app.services.kocp_equipment import kocp_asset_allowed, kocp_role_allowed

ROOT=Path(__file__).resolve().parents[1]


def test_production_groups_are_not_interchangeable():
    assert kocp_asset_allowed("COAL","COAL")
    assert not kocp_asset_allowed("COAL","OB")
    assert kocp_asset_allowed("OB","OB")
    assert not kocp_asset_allowed("OB","COAL")
    assert kocp_role_allowed("EICHER TIPPER","TRANSPORT")
    assert kocp_role_allowed("VOLVO TIPPER","TRANSPORT")
    assert kocp_role_allowed("EXCAVATOR VOLVO-480","LOADING")


def test_hsd_loads_all_assets_not_the_first_forty():
    ui=(ROOT/"app/static/simple_field_v1.js").read_text("utf-8")
    assert "const kocpAsset=siteId==='KOCP'&&w.dataset.kind==='ASSET';" in ui
    assert "limit:kocpAsset?'200':'40'" in ui
    assert "if(activity){params.set('activity',activity);params.set('role',role)}" in ui
    assert "lookup-summary" in ui
    assert "matching ${esc(label)}" in ui
    assert "x.group" in ui
    assert "lookupMarkup(`shAsset${i}`,'ASSET','Equipment')" in ui
    assert "state.module==='HSD'" not in ui[ui.index("function itemAllowed("):ui.index("function bindLookups(")]


def test_asset_picker_assets_are_cache_busted():
    page=(ROOT/"app/static/site.html").read_text("utf-8")
    css=(ROOT/"app/static/simple_field_v1.css").read_text("utf-8")
    assert "simple_field_v1.js?v=kocp-fuel-dashboard-r6" in page
    assert "simple_field_v1.css?v=kocp-fuel-dashboard-r6" in page
    assert ".lookup-summary" in css
    assert "max-height:min(52vh,400px)" in css


def test_hsd_post_accepts_site_assigned_equipment_independent_of_group():
    api=(ROOT/"app/routers/sites.py").read_text("utf-8")
    start=api.index("def create_hsd_transaction(")
    end=api.index("tx_id = f\"HSD-",start)
    block=api[start:end]
    assert "_site_equipment_assignment(db,site_id,p.assetId,p.operatingDate)" in block
    assert "kocp_asset_allowed" not in block
