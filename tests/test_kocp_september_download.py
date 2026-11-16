"""KOCP September-format Excel export contract; read-only test."""
import asyncio
from datetime import date
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Equipment
from app.site_models import Site, SiteTrip, SiteHsdTransaction, SiteAssetMeter
from app.services.kocp_report_formats import build

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _content(response):
    async def get_bytes():
        result = []
        async for chunk in response.body_iterator:
            result.append(chunk if isinstance(chunk, bytes) else chunk.encode())
        return b"".join(result)
    return asyncio.run(get_bytes())


def _numeric(root, addr):
    c = root.find(f'.//x:c[@r="{addr}"]', NS)
    if c is None: return None
    x = c.find("x:v", NS)
    return float(x.text) if x is not None else None


def test_six_management_sheets_match_uploaded_preview_and_keep_hmr_fuel_grain():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    day = date(2026, 11, 1)
    with Session(engine) as db:
        db.add(Site(site_id="KOCP", site_name="KOCP", short_name="KOCP", active=True))
        db.add_all([
            Equipment(machine_id="T1", door_no="V-2", type="TIPPER",
                      group="KOCP", ownership="NMTPL", active=True),
            Equipment(machine_id="E1", door_no="508", type="EXCAVATOR",
                      group="KOCP", ownership="NMTPL", active=True),
        ])
        db.add(SiteTrip(trip_id="TRIP-1", site_id="KOCP", operating_date=day,
                        shift="A", vehicle_id="T1", loading_equipment_id="E1",
                        trip_count=15, quantity_cum=Decimal("120"),
                        source_type="SHIFT_OB_CARD", source_record_uid="PAPER-1",
                        status="POSTED", entered_by="MIS"))
        db.add(SiteHsdTransaction(transaction_id="HSD-TEST", site_id="KOCP",
                                  operating_date=day, shift="A", asset_id="E1",
                                  transaction_type="ISSUE", litres=Decimal("40"),
                                  source_type="PORTAL", source_record_uid="HSD-1",
                                  entered_by="MIS", status="POSTED"))
        db.add(SiteAssetMeter(reading_id="HMR-TEST", site_id="KOCP",
                              operating_date=day, shift="A", asset_id="E1",
                              meter_type="HMR", opening_reading=Decimal("100"),
                              closing_reading=Decimal("102"), usage=Decimal("2"),
                              source_type="PORTAL", entered_by="MIS"))
        db.commit()
        out = build(db, day, day, "ALL")
        content = _content(out)
    with ZipFile(BytesIO(content)) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        names = [x.attrib["name"] for x in workbook.findall("x:sheets/x:sheet", NS)]
        assert names == [
            "README", "SEP OB TIPPER", "SEP OB TIPPER SUMMARY",
            "SEP EXCAVATOR", "SEP EXCAVATOR SUMMARY",
            "SEP LOADER", "SEP LOADER SUMMARY"
        ]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet5.xml"))
        merges = [x.attrib["ref"] for x in sheet.findall("x:mergeCells/x:mergeCell", NS)]
        assert "A1:K1" in merges and "A2:K2" in merges
        assert len(sheet.find("x:sheetData/x:row[@r='4']",NS)) == 11
        assert _numeric(sheet,"C5") == 15
        assert _numeric(sheet,"D5") == 120
        assert _numeric(sheet,"E5") == 2
        assert _numeric(sheet,"G5") == 40
        assert _numeric(sheet,"H5") == 8
        assert _numeric(sheet,"I5") == 60
        assert round(_numeric(sheet,"J5"),3) == 2.667
        assert _numeric(sheet,"K5") == 20
        # No manufactured loader productivity when no loader trips are posted.
        loader = ET.fromstring(archive.read("xl/worksheets/sheet7.xml"))
        assert loader.find("x:sheetData/x:row[@r='6']",NS) is None
    engine.dispose()
