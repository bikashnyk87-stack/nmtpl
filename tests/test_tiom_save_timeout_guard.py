"""Regression tests for read-only DPR timeouts and duplicate-safe MIS saves."""
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Equipment, Location, Product, ShiftMaster
from app.site_models import TiomMisReport
from app.routers.webapp import save_tiom_mis_report


ROOT=Path(__file__).parents[1]


def test_browser_recovers_timeout_without_encouraging_blind_duplicate():
    net=(ROOT/"app/static/net.js").read_text("utf-8")
    shell=(ROOT/"app/static/webapp.js").read_text("utf-8")
    mis=(ROOT/"app/static/tiom_phase1.js").read_text("utf-8")
    html=(ROOT/"app/static/index.html").read_text("utf-8")
    assert "CLIENT_TIMEOUT" in net
    assert "getTiomDprPreview" in shell and "options.timeoutMs=120000" in shell
    assert "options.timeoutMs=90000" in shell
    assert "m.startsWith('get')" in shell
    assert "before retrying" in shell
    assert "if(T.savingMis)return" in mis
    assert "payload.reportId=T.pendingMisReportId" in mis
    assert "tiomNewMisReportId()" in mis
    assert "getTiomMisReport({reportId:payload.reportId})" in mis
    assert "tiom-save-confirm-20261023-r1" in html
    assert "tiom-network-save-20261023-r1" in html
    assert "tiom-timeout-20261023-r1" in html


def test_retry_same_new_mis_id_does_not_create_duplicate():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        from datetime import time
        db.add_all([
            ShiftMaster(shift="A",start_time=time(5),end_time=time(13),scheduled_hours=8,active=True),
            Equipment(machine_id="DTV-TEST",type="Tipper",group="TRANSPORT",active=True),
            Equipment(machine_id="LOADER-TEST",type="Loader",group="LOADING",active=True),
            Product(product_id="OB",name="Overburden",active=True),
            Location(location_id="TEST-SOURCE",location_name="Mine Pit",active=True),
            Location(location_id="TEST-DEST",location_name="Waste Dump",active=True),
        ])
        db.flush()
        user=SimpleNamespace(admin=True,modules="PRODUCTION",shifts="ALL",login_id="TEST-USER")
        rid=str(uuid4())
        body={
            "reportId":rid,
            "date":"2026-10-11","shift":"A","vehicleId":"DTV-TEST",
            "rows":[{
                "materialId":"OB","sourceLocationId":"TEST-SOURCE",
                "destinationLocationId":"TEST-DEST","machineId":"LOADER-TEST",
                "loadingTime":"07:30",
            }],
        }
        result=save_tiom_mis_report(db,user,body,submit=True)
        db.commit()
        assert result["reportId"]==rid
        assert db.get(TiomMisReport,rid).status=="SUBMITTED"
        with pytest.raises(HTTPException) as caught:
            save_tiom_mis_report(db,user,body,submit=True)
        assert caught.value.status_code==409
        assert "already submitted" in caught.value.detail
        db.rollback()
        assert db.scalar(select(func.count()).select_from(TiomMisReport))==1
    engine.dispose()
