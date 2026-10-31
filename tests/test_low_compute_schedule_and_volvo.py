"""Read-only scheduling and isolated SQLite regressions for reduced Neon compute."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.routers import automation
from app.services import volvo_control, volvo_store
from app.volvo_models import VolvoReport, VolvoSync, VolvoVehicle, VolvoSyncControl
from scripts.render_sync_worker import IST, next_sync_slot

ROOT = Path(__file__).resolve().parents[1]


def test_wb_poll_slots_target_correct_operating_shift():
    tz=automation.IST
    at=lambda hour,minute:datetime(2026,10,31,hour,minute,tzinfo=tz)
    assert automation.wb_search_window(at(5,0))==("2026-10-31:C",datetime(2026,10,30).date(),"C")
    assert automation.wb_search_window(at(6,59))[2]=="C"
    assert automation.wb_search_window(at(7,0)) is None
    assert automation.wb_search_window(at(13,0))==("2026-10-31:A",datetime(2026,10,31).date(),"A")
    assert automation.wb_search_window(at(14,59))[2]=="A"
    assert automation.wb_search_window(at(15,0)) is None
    assert automation.wb_search_window(at(21,0))==("2026-10-31:B",datetime(2026,10,31).date(),"B")
    assert automation.wb_search_window(at(22,59))[2]=="B"
    assert automation.wb_search_window(at(23,0)) is None
    assert automation.WB_SEARCH_MINUTES == 120
    assert automation.WB_RETRY_SECONDS >= 600


def test_pc_sync_runs_hourly_only_6am_through_10pm():
    make=lambda h,m:datetime(2026,10,31,h,m,tzinfo=IST)
    assert next_sync_slot(make(5,20))==make(6,0)
    assert next_sync_slot(make(6,0))==make(6,0)
    assert next_sync_slot(make(16,23))==make(17,0)
    assert next_sync_slot(make(21,45))==make(22,0)
    assert next_sync_slot(make(22,1))==make(6,0)+timedelta(days=1)
    assert next_sync_slot(make(23,45))==make(6,0)+timedelta(days=1)
    assert next_sync_slot(make(2,0))==make(6,0)


def test_volvo_pause_persists_without_repeated_db_reads(monkeypatch):
    engine=create_engine("sqlite://",poolclass=StaticPool,connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(volvo_control,"_enabled",None)
    with Session(engine) as db:
        assert volvo_control.collection_enabled(db) is True
        assert volvo_control.set_collection_enabled(db,False,"admin") is False
    # Restart simulation: clear the in-memory cache, leave persisted row.
    monkeypatch.setattr(volvo_control,"_enabled",None)
    with Session(engine) as db:
        assert volvo_control.collection_enabled(db) is False
        assert volvo_control.collection_enabled(db) is False
        assert db.scalar(select(func.count()).select_from(VolvoSyncControl)) == 1
        assert volvo_control.set_collection_enabled(db,True,"admin") is True
        assert volvo_control.collection_enabled(db) is True
    engine.dispose()


def test_volvo_collector_skips_unchanged_vehicles_and_duplicate_reports(monkeypatch):
    engine=create_engine("sqlite://",poolclass=StaticPool,connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(volvo_store,"report_time",lambda row:datetime(2026,10,31,11,0,tzinfo=timezone.utc))
    class FakeClient:
        def fetch(self,kind):
            values={
                "vehicles":[{"vin":"WXYZ0123456789012","name":"Truck 001"}],
                "vehiclepositions":[{"vin":"WXYZ0123456789012","speed":12}],
                "vehiclestatuses":[{"vin":"WXYZ0123456789012","engine":True}],
            }
            return values.get(kind,[])
    # ENDPOINTS may have additional collection names (without rows).
    with Session(engine) as db:
        first=volvo_store.collect(db,FakeClient())
        assert first["changed_vehicles"]==1
        assert first["new_reports"]==2
        vehicle=db.get(VolvoVehicle,"WXYZ0123456789012")
        original=vehicle.last_seen
        second=volvo_store.collect(db,FakeClient())
        assert second["changed_vehicles"]==0
        assert second["new_reports"]==0
        db.refresh(vehicle)
        assert vehicle.last_seen==original
        assert db.scalar(select(func.count()).select_from(VolvoReport))==2
        assert db.scalar(select(func.count()).select_from(VolvoSync))==2
    engine.dispose()


def test_live_volvo_stop_button_and_backend_authorization_present():
    ui=(ROOT/"app/static/volvo.js").read_text("utf-8")
    api=(ROOT/"app/routers/volvo.py").read_text("utf-8")
    sync=(ROOT/"app/services/cloud_sync.py").read_text("utf-8")
    html=(ROOT/"app/static/index.html").read_text("utf-8")
    assert "Stop Volvo Sync" in ui
    assert "Resume Volvo Sync" in ui
    assert "collection-control" in ui
    assert "require(user, admin=True)" in api[api.index("def collection_control("):api.index("@router.get('/fleet')")]
    assert "csrf(request)" in api[api.index("def collection_control("):api.index("@router.get('/fleet')")]
    assert "CREATE TRIGGER" in sync and "existing_triggers" in sync
    assert 'DROP TRIGGER IF EXISTS' not in sync
    assert "tiom-volvo-r17-schedule" in html
