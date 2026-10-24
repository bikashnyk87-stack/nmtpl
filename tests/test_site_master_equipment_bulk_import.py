"""KOCP bulk Equipment imports: reproduce 131-row 500 and prove atomic fix."""
from datetime import date
from io import BytesIO
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Equipment
from app.site_models import EquipmentSiteAssignment, MasterImportBatch, MasterImportRow, Site
from app.routers import sites
from app.services.site_master_import import equipment_dimensions


def workbook(rows):
    wb=Workbook()
    ws=wb.active
    spec=sites.MASTER_TEMPLATES["EQUIPMENT"]
    ws.append(spec["headers"])
    for item in rows:ws.append([item.get(h) for h in spec["headers"]])
    data=BytesIO();wb.save(data)
    return data.getvalue()


def item(num,bucket="3.5",payload=None, machine=None):
    return {"Machine ID":machine or f"KOCP-TST-{num:03d}",
            "Door No":f"DOOR-{num}","Vehicle No":f"OD-TST-{num:03d}",
            "Type":"TIPPER","Group":"TRANSPORT",
            "Make Model":"Test Truck","Bucket CuM":bucket,
            "Rated Payload T":payload,"Ownership":"OWN",
            "Effective From":"2026-10-01","Active":"TRUE"}


def setup(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},
                         poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for name in ("KOCP","SOCP","TIOM"):
            db.add(Site(site_id=name,site_name=name,short_name=name,
                        timezone="Asia/Kolkata",active=True))
        db.commit()
    app=FastAPI()
    app.include_router(sites.router)
    def sess():
        with Session(engine) as db:yield db
    app.dependency_overrides[sites.get_db]=sess
    monkeypatch.setattr(sites,"csrf",lambda request:None)
    monkeypatch.setattr(sites,"get_user",lambda db,request:
                        SimpleNamespace(admin=True,login_id="KOCP-TEST"))
    monkeypatch.setattr(sites,"require_site",lambda db,user,site_id:site_id)
    monkeypatch.setattr(sites,"require_permission",lambda db,user,site_id,module,action:None)
    return engine,app


def test_mixed_units_are_explicit_not_guessed():
    assert equipment_dimensions(item(1,"31 CUM (HIP VOLUME)/40.30 MT"))==(31.0,40.3,True)
    assert equipment_dimensions(item(1,"3.5",None))==(3.5,None,False)
    assert equipment_dimensions(item(1,"3.5 CuM","40.3 MT"))==(3.5,40.3,False)
    assert equipment_dimensions(item(1,"31 CUM/40.30 MT",40.30))==(31.0,40.30,True)
    from pytest import raises
    with raises(ValueError,match="conflicts"):
        equipment_dimensions(item(1,"31 CUM/40.30 MT",35))
    with raises(ValueError,match="Bucket CuM"):
        equipment_dimensions(item(1,"31/40.30"))


def test_131_row_kocp_workbook_preview_confirm_and_no_duplicate(monkeypatch):
    engine,app=setup(monkeypatch)
    rows=[item(i, "31 CUM (HIP VOLUME)/40.30 MT" if i==1 else "3.5",
               None if i==1 else 12.5) for i in range(1,132)]
    with TestClient(app) as client:
        response=client.post("/api/sites/KOCP/masters/EQUIPMENT/preview",
            files={"file":("NMTPL_KOCP_EQUIPMENT_Template.xlsx",workbook(rows),
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert response.status_code==200,response.text
        data=response.json()
        assert data["totalRows"]==131 and data["errorRows"]==0
        batch=data["batchId"]
        confirmed=client.post(f"/api/sites/KOCP/masters/imports/{batch}/confirm")
        assert confirmed.status_code==200,confirmed.text
        assert confirmed.json()["created"]==131
        assert confirmed.json()["rows"]==131
        again=client.post(f"/api/sites/KOCP/masters/imports/{batch}/confirm")
        assert again.status_code==409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Equipment))==131
        row=db.get(Equipment,"KOCP-TST-001")
        assert row.bucket_cum==31
        assert row.rated_payload_t==40.30
        assert db.get(MasterImportBatch,batch).status=="IMPORTED"
        assert db.scalar(select(func.count()).select_from(EquipmentSiteAssignment).where(
            EquipmentSiteAssignment.site_id=="KOCP"))==131
    engine.dispose()


def test_old_preview_batch_is_revalidated_and_atomic(monkeypatch):
    engine,app=setup(monkeypatch)
    # Simulate a 131-row PREVIEW created before the new validation existed.
    batch="MIMP-KOCP-OLD-TEST"
    with Session(engine) as db:
        db.add(MasterImportBatch(batch_id=batch,site_id="KOCP",
            master_type="EQUIPMENT",file_name="old.xlsx",file_hash="old",
            status="PREVIEW",total_rows=131,valid_rows=131,error_rows=0,
            uploaded_by="KOCP-TEST"))
        for i in range(1,132):
            import json
            entry=item(i,"31 CUM (HIP VOLUME)/40.30 MT" if i==131 else "3.5")
            if i==131:
                entry["Bucket CuM"]="capacity 31 hip 40t"  # no trustworthy units
            db.add(MasterImportRow(batch_id=batch,row_no=i+1,
                row_json=json.dumps(entry),status="VALID"))
        db.commit()
    with TestClient(app) as client:
        reply=client.post(f"/api/sites/KOCP/masters/imports/{batch}/confirm")
        assert reply.status_code==422,reply.text
        assert "Excel row 132" in reply.text
        assert "No rows from this batch were imported." in reply.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Equipment))==0
        assert db.get(MasterImportBatch,batch).status=="PREVIEW"
    engine.dispose()


def test_cross_site_global_equipment_is_not_overwritten(monkeypatch):
    engine,app=setup(monkeypatch)
    with Session(engine) as db:
        db.add(Equipment(machine_id="SHARED-100",type="EXCAVATOR",
            group="LOADING",bucket_cum=5.0,active=True,make_model="OLD"))
        db.add(EquipmentSiteAssignment(machine_id="SHARED-100",site_id="TIOM",
            effective_from=date(2026,1,1),active=True,source="MASTER"))
        db.commit()
    change=item(1,"31 CUM (HIP VOLUME)/40.30 MT",machine="SHARED-100")
    with TestClient(app) as client:
        preview=client.post("/api/sites/KOCP/masters/EQUIPMENT/preview",
            files={"file":("shared.xlsx",workbook([change]),
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert preview.status_code==200
        assert preview.json()["errorRows"]==1
        assert "another site" in str(preview.json()["errors"])
        response=client.post("/api/sites/KOCP/masters/imports/"
                             +preview.json()["batchId"]+"/confirm")
        assert response.status_code==409
    with Session(engine) as db:
        shared=db.get(Equipment,"SHARED-100")
        assert shared.type=="EXCAVATOR" and shared.bucket_cum==5.0
        assert db.scalar(select(func.count()).select_from(EquipmentSiteAssignment).where(
            EquipmentSiteAssignment.site_id=="KOCP"))==0
    engine.dispose()
