"""Separate Coal Loader/Excavator counts never increase posted production."""
from datetime import date, time
from types import SimpleNamespace
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
from fastapi import HTTPException
import pytest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Equipment
from app.site_models import (EquipmentSiteAssignment, Site, SiteShift,
                             SiteCoalLoadingCount, SiteTrip)
from app.routers import kocp_shift_register as registers
from app.routers import site_ops


DAY = date(2026, 11, 19)


def test_coal_loading_count_is_independent_editable_and_reconciled(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    actor = SimpleNamespace(admin=True, login_id="MIS")
    monkeypatch.setattr(registers, "_auth", lambda *args: actor)
    with Session(engine) as db:
        db.add_all([
            Site(site_id="KOCP", site_name="KOCP", short_name="KOCP", active=True),
            SiteShift(site_id="KOCP", shift="A", start_time=time(5),
                      end_time=time(13), scheduled_hours=8),
            Equipment(machine_id="L1", type="LOADER", group="COAL", active=True),
            Equipment(machine_id="E1", type="EXCAVATOR", group="COAL", active=True),
            Equipment(machine_id="T1", type="TIPPER", group="COAL", active=True),
            EquipmentSiteAssignment(machine_id="L1", site_id="KOCP",
                                    effective_from=DAY),
            EquipmentSiteAssignment(machine_id="E1", site_id="KOCP",
                                    effective_from=DAY),
            EquipmentSiteAssignment(machine_id="T1", site_id="KOCP",
                                    effective_from=DAY),
        ])
        db.commit()
        first = registers.save_coal_loading_counts(
            {"operatingDate": DAY.isoformat(), "shift": "A",
             "rows": [{"machineId": "L1", "loadedTrips": 12}]}, None, db)
        assert first["saved"] == 1
        assert first["rows"][0]["status"] == "WAITING_FOR_TIPPER"
        assert db.scalar(select(SiteTrip.trip_id)) is None
        version = first["rows"][0]["version"]
        assert registers.save_coal_loading_counts(
            {"operatingDate": DAY.isoformat(), "shift": "A",
             "rows": [{"machineId": "L1", "loadedTrips": 12}]}, None, db)["saved"] == 0
        with pytest.raises(HTTPException) as error:
            registers.save_coal_loading_counts(
                {"operatingDate": DAY.isoformat(), "shift": "A",
                 "rows": [{"machineId": "T1", "loadedTrips": 12}]}, None, db)
        assert error.value.status_code == 422
        with pytest.raises(HTTPException) as error:
            registers.save_coal_loading_counts(
                {"operatingDate": DAY.isoformat(), "shift": "A",
                 "rows": [{"machineId": "E1", "loadedTrips": 3},
                          {"machineId": "E1", "loadedTrips": 3}]}, None, db)
        assert error.value.status_code == 422
        db.rollback()
        db.add(SiteTrip(trip_id="T-1",site_id="KOCP",operating_date=DAY,
                        shift="A",vehicle_id="T1",loading_equipment_id="L1",
                        trip_count=12,source_type="SHIFT_COAL_REGISTER",
                        quantity_mt=Decimal("420"),status="POSTED",entered_by="MIS"))
        db.commit()
        comparison = registers.coal_loading_counts(None, DAY, "A", db)
        assert comparison["rows"][0]["status"] == "MATCH"
        assert comparison["totals"]["loadedTrips"] == 12
        assert comparison["totals"]["postedMappedTipperTrips"] == 12
        with pytest.raises(HTTPException) as error:
            registers.save_coal_loading_counts(
                {"operatingDate": DAY.isoformat(), "shift": "A",
                 "rows": [{"machineId": "L1", "loadedTrips": 10,
                            "expectedVersion": version}]}, None, db)
        assert error.value.status_code == 422  # reason required
        db.rollback()
        changed = registers.save_coal_loading_counts(
            {"operatingDate": DAY.isoformat(), "shift": "A",
             "reason": "Corrected against paper loader card",
             "rows": [{"machineId": "L1", "loadedTrips": 10,
                        "expectedVersion": version}]}, None, db)
        assert changed["rows"][0]["status"] == "DIFFERENCE"
        assert changed["rows"][0]["difference"] == -2
        with pytest.raises(HTTPException) as error:
            registers.save_coal_loading_counts(
                {"operatingDate": DAY.isoformat(), "shift": "A",
                 "reason": "Old version cannot overwrite current count",
                 "rows": [{"machineId": "L1", "loadedTrips": 11,
                            "expectedVersion": version}]}, None, db)
        assert error.value.status_code == 409
        db.rollback()
        # Real production remains one source trip and unchanged 420 MT.
        t = db.get(SiteTrip, "T-1")
        assert t.trip_count == 12 and t.quantity_mt == Decimal("420")
        assert len(db.scalars(select(SiteCoalLoadingCount)).all()) == 1
    engine.dispose()


def test_machine_count_is_reported_separately_without_production_duplication(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    actor = SimpleNamespace(admin=True, login_id="MIS")
    monkeypatch.setattr(site_ops, "get_user", lambda *args: actor)
    monkeypatch.setattr(site_ops, "require_site", lambda *args: "KOCP")
    with Session(engine) as db:
        db.add_all([
            Site(site_id="KOCP",site_name="KOCP",short_name="KOCP",active=True),
            Equipment(machine_id="L1",type="LOADER",group="COAL",active=True),
            Equipment(machine_id="T1",type="TIPPER",group="COAL",active=True),
            SiteCoalLoadingCount(count_id="CLD-KOCP-TEST",site_id="KOCP",
                operating_date=DAY,shift="A",machine_id="L1",loaded_trips=20,
                entered_by="MIS",version=1),
            SiteTrip(trip_id="TEST-TRIP",site_id="KOCP",operating_date=DAY,
                shift="A",vehicle_id="T1",loading_equipment_id="L1",
                trip_count=18,status="POSTED",source_type="SHIFT_COAL_REGISTER",
                entered_by="MIS"),
        ])
        db.commit()
        response = site_ops.kocp_comprehensive_report(object(), DAY, DAY, "COAL_LOADING", db)
        import asyncio
        async def payload():
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            return b"".join(chunks)
        excel = asyncio.run(payload())
        with ZipFile(BytesIO(excel)) as archive:
            from xml.etree import ElementTree as ET
            root = ET.fromstring(archive.read("xl/workbook.xml"))
            namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            names = [el.attrib["name"] for el in root.findall("x:sheets/x:sheet", namespace)]
            assert "Coal Loading Count Check" in names
        assert db.get(SiteTrip, "TEST-TRIP").trip_count == 18
    engine.dispose()
