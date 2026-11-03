"""Site Master access must remain site-scoped and not make Despatch admin-only."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.sites import _normalise_access_plan


ROOT = Path(__file__).resolve().parents[1]


class SiteDatabase:
    def scalars(self, query):
        # Active site catalogue returned to the normaliser.
        return iter(("TIOM", "KOCP", "SOCP"))


def test_tiom_despatch_role_grants_are_valid_at_their_single_required_action():
    db = SiteDatabase()
    sites, known, default, parsed = _normalise_access_plan(
        db, ["TIOM"], [
            "TIOM.PRODUCTION.VIEW", "TIOM.DESPATCH_EVIDENCE.CREATE",
            "TIOM.DESPATCH_IMPORT.CREATE", "TIOM.DESPATCH_REVIEW.EDIT",
        ], "TIOM"
    )
    assert sites == {"TIOM"}
    assert known == {"TIOM", "KOCP", "SOCP"}
    assert default == "TIOM"
    assert {p[3] for p in parsed} == {
        "TIOM.PRODUCTION.VIEW", "TIOM.DESPATCH_EVIDENCE.CREATE",
        "TIOM.DESPATCH_IMPORT.CREATE", "TIOM.DESPATCH_REVIEW.EDIT",
    }


@pytest.mark.parametrize("permission", [
    "TIOM.DESPATCH_EVIDENCE.APPROVE",
    "TIOM.DESPATCH_IMPORT.EDIT",
    "TIOM.DESPATCH_REVIEW.CREATE",
    "KOCP.DESPATCH_EVIDENCE.CREATE",
    "SOCP.DESPATCH_IMPORT.CREATE",
    "KOCP.MASTERS.CREATE",  # cannot grant a site that was not assigned
])
def test_other_sites_and_incorrect_despatch_actions_are_rejected(permission):
    with pytest.raises(HTTPException) as exc:
        _normalise_access_plan(SiteDatabase(), ["TIOM"], [permission], "TIOM")
    assert exc.value.status_code == 422


def test_master_access_ui_is_shared_by_all_sites_and_preserves_other_site_grants():
    html=(ROOT/"app/static/site.html").read_text("utf-8")
    js=(ROOT/"app/static/site_access_master.js").read_text("utf-8")
    central=(ROOT/"app/static/admin_master_ops.js").read_text("utf-8")
    assert "site_access_master.js?v=site-permissions-20261103-r1" in html
    assert "state.module!=='MASTERS'" in js
    assert "isManagement" in js
    assert "api('/api/sites/admin/access')" in js
    assert "permissions=(latest.permissions||[]).filter(x=>!x.startsWith(siteId+'.'))" in js
    assert "if(enabled)sites.add(siteId);else sites.delete(siteId);" in js
    assert "TIOM" in js and "DESPATCH_EVIDENCE" in js
    assert "DESPATCH_EVIDENCE" in central and "DESPATCH_REVIEW" in central
