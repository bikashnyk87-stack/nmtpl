"""Source-backed KOCP MIS export: complete rows and independent meter/fuel grain."""
import asyncio
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Equipment
from app.site_models import (
    Site, SiteTrip, SiteHsdTransaction, SiteAssetMeter,
    SiteShiftTripCard, SiteShiftTripCardLine,
)
from app.routers import site_ops

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


async def _content(response):
    parts = []
    async for part in response.body_iterator:
        parts.append(part if isinstance(part, bytes) else part.encode())
    return b"".join(parts)


def _sheet_xml(archive, idx):
    return ET.fromstring(archive.read(f"xl/worksheets/sheet{idx}.xml"))


def _cell_number(root, address):
    cell = root.find(f'.//x:c[@r="{address}"]', NS)
    return float(cell.find("x:v", NS).text) if cell is not None and cell.find("x:v", NS) is not None else None


def test_complete_report_keeps_trip_meter_fuel_and_unverified_source_separate(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(site_ops, "get_user", lambda db, request: SimpleNamespace(admin=True, login_id="CHECKER"))
    monkeypatch.setattr(site_ops, "require_site", lambda db, user, site_id: "KOCP")
    day = date(2026, 11, 16)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP", site_name="KOCP", short_name="KOCP", active=True))
        db.add_all([
            Equipment(machine_id="T1", door_no="V-1", type="TIPPER", group="OB", active=True),
            Equipment(machine_id="E1", door_no="508", type="EXCAVATOR", group="OB", active=True),
        ])
        db.add(SiteTrip(
            trip_id="POSTED-1", site_id="KOCP", operating_date=day,
            shift="A", vehicle_id="T1", loading_equipment_id="E1",
            trip_count=15, quantity_cum=Decimal("120"), quantity_mt=None,
            source_type="SHIFT_OB_CARD", source_record_uid="PAPER-POSTED",
            status="POSTED", entered_by="MIS"))
        db.add(SiteHsdTransaction(
            transaction_id="FUEL-1", site_id="KOCP", operating_date=day,
            shift="A", asset_id="E1", transaction_type="ISSUE",
            litres=Decimal("40"), status="POSTED",
            source_type="PORTAL", source_record_uid="FUEL-1", entered_by="MIS"))
        db.add(SiteAssetMeter(
            reading_id="METER-1", site_id="KOCP", operating_date=day,
            shift="A", asset_id="E1", meter_type="HMR",
            opening_reading=Decimal("100"), closing_reading=Decimal("102"),
            usage=Decimal("2"), source_type="PORTAL", entered_by="MIS"))
        db.add(SiteShiftTripCard(
            card_id="CARD-PENDING", site_id="KOCP", kind="OB",
            operating_date=day, shift="A", client_key="PENDING-TEST",
            vehicle_id="T1", status="SUBMITTED", version=2, entered_by="MIS"))
        db.add(SiteShiftTripCardLine(
            line_id="LINE-PENDING", card_id="CARD-PENDING",
            line_no=1, excavator_id="E1", trip_count=5))
        db.commit()
        response = site_ops.kocp_comprehensive_report(
            object(), day, day, "ALL", db)
        payload = asyncio.run(_content(response))
    with ZipFile(BytesIO(payload)) as z:
        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        sheet_names = [e.attrib["name"] for e in workbook.findall("x:sheets/x:sheet", NS)]
        expected = {"Read Me", "Production Trips", "Daily OB Tipper", "Daily Excavator",
                    "Daily Loader", "HMR KMR Register", "HSD Ledger", "HSD by Equipment",
                    "HSD by Shift", "Source Cards", "Source Card Lines", "MCL Rules",
                    "Monthly Equipment Totals"}
        assert expected.issubset(set(sheet_names))
        excavator = _sheet_xml(z, sheet_names.index("Daily Excavator") + 1)
        assert _cell_number(excavator, "F2") == 15
        assert _cell_number(excavator, "H2") == 120
        assert _cell_number(excavator, "I2") == 2
        assert _cell_number(excavator, "K2") == 40
        assert _cell_number(excavator, "M2") == 60
        source = _sheet_xml(z, sheet_names.index("Source Card Lines") + 1)
        assert _cell_number(source, "Q2") == 5
        # The unverified paper trips do NOT increase already-posted trip totals.
        production = _sheet_xml(z, sheet_names.index("Production Trips") + 1)
        assert _cell_number(production, "F2") == 15
        assert len(production.findall("x:sheetData/x:row", NS)) == 2
    engine.dispose()
