from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from io import BytesIO

from openpyxl import load_workbook

from app.routers.tiom_despatch import _amns_material, _amns_buyer
from app.services.tiom_despatch_client_layout import reportable_category
from app.services.tiom_despatch_client_reports import build_client_workbook
from app.services.tiom_despatch_source_adapters import parse_despatch_sources


def _trip(number, day):
    return SimpleNamespace(
        epass_no=f"L102604962/{number}", report_date=day,
        permit_no="L102604962", permit_qty=Decimal("0"),
        buyer=_amns_buyer("DNA Minerals"), destination="Bongobari(Purulia)",
        material_grade=_amns_material("5-18mm(62-65)", "", day),
        vehicle_no="OD09Z1234", transporter="TEST", stack_no="",
        consignee="123013638611/DNA MINERALS PVT LTD",
        tare_mt=Decimal("14"), gross_mt=Decimal("44"),
        net_mt=Decimal("30"), dispatch_time="11:35:20", status="ACTIVE",
    )


def test_confirmed_nov_grade_exports_captive_report():
    trip = _trip(8, date(2026, 11, 1))
    assert reportable_category(trip)
    stream, totals = build_client_workbook(
        "despatch", [trip], date(2026, 11, 1), date(2026, 11, 4))
    book = load_workbook(BytesIO(stream.getvalue()))
    sheet = book["DESTINATION WISE"]
    assert any(cell.value == "5-18mm\n(62-65)" for row in sheet.iter_rows(min_row=3, max_row=3) for cell in row)
    assert totals["quantityMt"] == 30.0


def test_trip_report_includes_source_wb_time():
    trip = _trip(8, date(2026, 11, 1))
    stream, _ = build_client_workbook(
        "trip", [trip], date(2026, 11, 1), date(2026, 11, 4))
    book = load_workbook(BytesIO(stream.getvalue()))
    sheet = book["01.11.26"]
    assert sheet["P2"].value == "WB Time"
    assert sheet["P3"].value == "11:35:20"


def test_wb_time_and_permitted_quantity_header_aliases():
    csv_bytes = (
        "E-Pass No,Permit No,Permitted Quantity,Vehicle RegNo,"
        "Tare Wt,Gross Wt,Net Wt,Date,Weighbridge Time\n"
        "L102604962/8,L102604962,800,OD09Z1234,14,44,30,2026-11-01,11:35:20\n"
    ).encode()
    rows = parse_despatch_sources(csv_bytes, "test.csv")
    assert rows[0]["permit_qty"] == "800"
    assert rows[0]["dispatch_time"] == "11:35:20"
