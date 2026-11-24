"""TIOM Masters: assigned module permits data maintenance, not user administration."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Product, MasterOption, ShiftRotation
from app.routers import webapp

ROOT=Path(__file__).parents[1]


def actor(modules="", admin=False):
    return SimpleNamespace(login_id="mis.tiom", name="MIS", modules=modules,
                           shifts="A,B,C", admin=admin, active=True)


@pytest.fixture
def db():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},
                         poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
        session.rollback()
    engine.dispose()


def test_mis_masters_module_can_create_and_edit_product(db):
    user=actor("PRODUCTION,MASTERS")
    created=webapp.save_master_record(db,user,{"table":"PRODUCT",
        "intent":"create","row":{"id":"TEST_MIS_M","name":"Test ROM", "active":True}})
    db.commit()
    assert created["ok"]
    record=db.get(Product,"TEST_MIS_M")
    assert record.name=="Test ROM" and record.active
    edited=webapp.save_master_record(db,user,{"table":"PRODUCT",
        "intent":"update","row":{"id":"TEST_MIS_M","name":"Test ROM corrected","active":False}})
    db.commit()
    db.refresh(record)
    assert edited["ok"] and record.name=="Test ROM corrected"
    assert record.active is False


def test_mis_masters_module_can_add_dropdown_and_rotation_team(db):
    user=actor("MASTERS")
    x=webapp.save_master_option(db,user,{"category":"PERSON.department","value":"Dispatch"})
    assert x["ok"]
    db.flush()
    assert db.get(MasterOption,("PERSON.department","Dispatch")) is not None
    team=webapp.save_rotation_team(db,user,{"id":"TESTMIS","name":"MIS team",
                                    "shift":"A","monday":"2026-11-23"})
    db.flush()
    assert team["ok"]
    assert db.get(ShiftRotation,"TESTMIS").team_name=="MIS team"


def test_no_masters_permission_cannot_write_even_if_client_sends_rpc(db):
    user=actor("PRODUCTION,DASHBOARD")
    operations=(
      (webapp.save_master_record,{"table":"PRODUCT","intent":"create",
                                 "row":{"id":"BYPASS","name":"Not permitted","active":True}}),
      (webapp.save_master_option,{"category":"PERSON.role","value":"Not permitted"}),
      (webapp.save_rotation_team,{"id":"NOMIS","name":"Not permitted",
                                  "shift":"A","monday":"2026-11-23"}),
    )
    for func,payload in operations:
        with pytest.raises(HTTPException) as exc:
            func(db,user,payload)
        assert exc.value.status_code==403
    assert db.get(Product,"BYPASS") is None


def test_nonmanagement_masters_cannot_manage_user_accounts(db):
    with pytest.raises(HTTPException) as exc:
        webapp.user_admin(db,actor("MASTERS"),"getUserAdminData",[])
    assert exc.value.status_code==403


def test_existing_management_still_can_edit_masters(db):
    manager=actor("",admin=True)
    result=webapp.save_master_record(db,manager,{"table":"PRODUCT","intent":"create",
         "row":{"id":"ADMIN_M","name":"Manager Entry","active":True}})
    assert result["ok"]


def test_masters_ui_controls_depend_on_module_not_management():
    js=(ROOT/"app/static/workspace.js").read_text(encoding="utf8")
    assert "function canEditTiomMasters()" in js
    assert "modules?.includes('MASTERS')" in js
    assert "canEditTiomMasters()?'<button class=\"btn primary\"" in js
    assert "if(canEditTiomMasters())headers.push('Action')" in js
    assert "if(canEditTiomMasters())cells.push(" in js
    assert "if(!canEditTiomMasters())" in js
    assert "S.boot.user.isManagement?'<button class=\"btn primary\" onclick=\"editMaster(-1)" not in js


def test_masters_script_cache_changed_for_existing_sessions():
    html=(ROOT/"app/static/index.html").read_text(encoding="utf8")
    assert "workspace.js?v=mis-masters-write-20261124" in html
