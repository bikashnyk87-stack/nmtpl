"""TIOM Despatch MIS roles are independent from management permission."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import tiom_despatch


@pytest.fixture
def actor(monkeypatch):
    user = SimpleNamespace(admin=False, modules="PRODUCTION")
    monkeypatch.setattr(tiom_despatch, "get_user", lambda db, request: user)
    monkeypatch.setattr(tiom_despatch, "require_site", lambda db, user, site: site)
    monkeypatch.setattr(tiom_despatch, "has_permission", lambda *args: False)
    return user


@pytest.mark.parametrize("permission", ["DESPATCH_EVIDENCE", "DESPATCH_IMPORT", "DESPATCH_REVIEW"])
def test_grant_required_for_each_despatch_operation(actor, permission):
    with pytest.raises(HTTPException) as exc:
        tiom_despatch._user(None, None, permission=permission)
    assert exc.value.status_code == 403
    assert "Ask management" in exc.value.detail
    actor.modules += "," + permission
    assert tiom_despatch._user(None, None, permission=permission) is actor


def test_import_does_not_grant_review_or_evidence(actor):
    actor.modules += ",DESPATCH_IMPORT"
    assert tiom_despatch._user(None, None, permission="DESPATCH_IMPORT") is actor
    for permission in ("DESPATCH_EVIDENCE", "DESPATCH_REVIEW"):
        with pytest.raises(HTTPException) as exc:
            tiom_despatch._user(None, None, permission=permission)
        assert exc.value.status_code == 403


def test_management_actions_stay_admin_only(actor):
    actor.modules += ",DESPATCH_EVIDENCE,DESPATCH_IMPORT,DESPATCH_REVIEW"
    with pytest.raises(HTTPException) as exc:
        tiom_despatch._user(None, None, edit=True)
    assert exc.value.status_code == 403


def test_admin_keeps_full_access(actor):
    actor.admin = True
    actor.modules = ""
    assert tiom_despatch._user(None, None, permission="DESPATCH_EVIDENCE") is actor
    assert tiom_despatch._user(None, None, edit=True) is actor


def test_production_is_still_required(actor):
    actor.modules = "DESPATCH_EVIDENCE"
    with pytest.raises(HTTPException) as exc:
        tiom_despatch._user(None, None, permission="DESPATCH_EVIDENCE")
    assert exc.value.status_code == 403

def test_normalised_site_grant_authorises_despatch_without_legacy_roles(actor, monkeypatch):
    actor.modules = ""
    monkeypatch.setattr(tiom_despatch, "has_permission",
                        lambda db, user, site, module, action:
                        site == "TIOM" and (module, action) in {
                            ("PRODUCTION", "VIEW"), ("DESPATCH_EVIDENCE", "CREATE")
                        })
    assert tiom_despatch._user(None, None, permission="DESPATCH_EVIDENCE") is actor
    with pytest.raises(HTTPException) as exc:
        tiom_despatch._user(None, None, permission="DESPATCH_IMPORT")
    assert exc.value.status_code == 403


def test_unassigned_site_blocks_legacy_despatch(actor, monkeypatch):
    monkeypatch.setattr(tiom_despatch, "require_site",
                        lambda *args: (_ for _ in ()).throw(HTTPException(403, "Site unassigned")))
    actor.modules += ",DESPATCH_EVIDENCE"
    with pytest.raises(HTTPException) as exc:
        tiom_despatch._user(None, None, permission="DESPATCH_EVIDENCE")
    assert exc.value.status_code == 403
