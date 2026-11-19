"""WB Time and E-Pass date are visible in Trip Summary without inventing source data."""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.services.tiom_despatch_client_reports import build_client_workbook


def item(day, epass, clock):
    return SimpleNamespace(
        report_date=day, epass_no=epass, permit_no=epass.split("/")[0],
        permit_qty=Decimal("8000.620"), buyer="PH ASSOCIATES PRIVATE LIMITED",
        destination="Palaspanga", material_grade="5-18mm(60-62)",
        vehicle_no="OD09P7267", transporter="RIDHICON LOGISTICS PRIVATE LIMITED",
        stack_no="J26085113340", consignee="081813771711/PH ASSOCIATES PRIVATE LIMITED",
        tare_mt=Decimal("15.000"), gross_mt=Decimal("45.000"),
        net_mt=Decimal("30.000"), dispatch_time=clock,
        status="ACTIVE", source="Date Wise source",
    )


def test_front_tab_and_existing_detail_show_validated_date_and_wb_time():
    rows=[
        item(date(2026,11,4), "L102604966/123", ""),
        item(date(2026,11,5), "L102604966/124", "10:17:30:927AM"),
        item(date(2026,11,6), "L102604966/125", "1:03:10:230PM"),
    ]
    buffer, counts=build_client_workbook(
        "trip", rows, date(2026,11,4), date(2026,11,6)
    )
    assert counts["trips"]==3
    book=load_workbook(BytesIO(buffer.getvalue()))
    try:
        assert book.sheetnames==[
            "WB Date-Time", "04.11.26", "05.11.26", "06.11.26",
            "Cummulative", "Cancellation",
        ]
        overview=book["WB Date-Time"]
        assert overview["A3"].value=="E-Pass Date"
        assert overview["B3"].value=="WB Time (source)"
        assert overview["A4"].value==datetime(2026,11,6)
        assert overview["B4"].value=="1:03:10:230PM"
        assert overview["C4"].value=="L102604966/125"
        assert overview["A5"].value==datetime(2026,11,5)
        assert overview["B5"].value=="10:17:30:927AM"
        assert overview["A6"].value==datetime(2026,11,4)
        assert overview["B6"].value is None
        assert overview["H6"].value=="NOT IN SOURCE"
        assert "1 missing in imported source" in overview["A2"].value
        for day, time in ((4,None),(5,"10:17:30:927AM"),(6,"1:03:10:230PM")):
            sheet=book[f"{day:02d}.11.26"]
            assert sheet["O2"].value=="Date "
            assert sheet["P2"].value=="WB Time"
            assert sheet["O3"].value==datetime(2026,11,day)
            assert sheet["O3"].number_format=="DD-MM-YYYY"
            assert sheet["P3"].value==time
        assert [book["Cummulative"][f"P{r}"].value for r in range(3,6)] == [
            None, "10:17:30:927AM", "1:03:10:230PM",
        ]
        # The client A:P column positions, totals and old sheets are untouched.
        assert book["06.11.26"]["C2"].value=="Permit Qty."
        assert book["06.11.26"]["N3"].value==30.0
        assert book["Cummulative"]["N1"].value==3
    finally:
        book.close()


def test_no_fabricated_wb_time_for_earlier_source_days():
    rows=[item(date(2026,11,1),"L102604966/1","")]
    buffer,_=build_client_workbook("trip",rows,date(2026,11,1),date(2026,11,1))
    book=load_workbook(BytesIO(buffer.getvalue()))
    try:
        assert book["WB Date-Time"]["B4"].value is None
        assert book["WB Date-Time"]["H4"].value=="NOT IN SOURCE"
        assert book["01.11.26"]["P3"].value is None
        assert book["01.11.26"]["O3"].value==datetime(2026,11,1)
    finally:
        book.close()
