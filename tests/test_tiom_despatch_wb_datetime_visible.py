"""WB Time belongs in column P of the existing Trip Summary — no extra tabs."""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.services.tiom_despatch_client_reports import build_client_workbook


def trip(day, epass, clock):
    return SimpleNamespace(
        report_date=day, epass_no=epass, permit_no=epass.split("/")[0],
        permit_qty=Decimal("8000.620"), buyer="PH ASSOCIATES PRIVATE LIMITED",
        destination="Palaspanga", material_grade="5-18mm(60-62)",
        vehicle_no="OD09P7267", transporter="RIDHICON LOGISTICS PRIVATE LIMITED",
        stack_no="J26085113340", consignee="081813771711/PH ASSOCIATES PRIVATE LIMITED",
        tare_mt=Decimal("15.000"), gross_mt=Decimal("45.000"),
        net_mt=Decimal("30.000"), dispatch_time=clock,
        status="ACTIVE", source="Verified Date Wise E-Pass source",
    )


def test_existing_daily_and_cumulative_columns_only_no_new_tab():
    rows=[
        trip(date(2026,11,1), "L102604966/123", ""),
        trip(date(2026,11,2), "L102604966/124", "10:17:30:927AM"),
        trip(date(2026,11,3), "L102604966/125", "1:03:10:230PM"),
    ]
    buffer, counts=build_client_workbook(
        "trip", rows, date(2026,11,1), date(2026,11,3)
    )
    assert counts["trips"]==3
    book=load_workbook(BytesIO(buffer.getvalue()))
    try:
        assert book.sheetnames==[
            "01.11.26", "02.11.26", "03.11.26", "Cummulative", "Cancellation",
        ]
        assert "WB Date-Time" not in book.sheetnames
        for day,time in ((1,None),(2,"10:17:30:927AM"),(3,"1:03:10:230PM")):
            ws=book[f"{day:02d}.11.26"]
            assert ws["O2"].value=="Date "
            assert ws["P2"].value=="WB Time"
            assert ws["O3"].value==datetime(2026,11,day)
            assert ws["O3"].number_format=="DD-MM-YYYY"
            assert ws["P3"].value==time
            assert ws["C2"].value=="Permit Qty."
        cum=book["Cummulative"]
        assert [cum[f"P{row}"].value for row in range(3,6)]==[
            None,"10:17:30:927AM","1:03:10:230PM",
        ]
        assert [cum[f"O{row}"].value for row in range(3,6)]==[
            datetime(2026,11,1),datetime(2026,11,2),datetime(2026,11,3),
        ]
    finally:
        book.close()


def test_missing_time_is_not_invented():
    rows=[trip(date(2026,11,1),"L102604966/1","")]
    buffer,_=build_client_workbook("trip",rows,date(2026,11,1),date(2026,11,1))
    book=load_workbook(BytesIO(buffer.getvalue()))
    try:
        assert book.sheetnames==["01.11.26","Cummulative","Cancellation"]
        assert book["01.11.26"]["P3"].value is None
        assert book["Cummulative"]["P3"].value is None
        assert book["01.11.26"]["O3"].value==datetime(2026,11,1)
    finally:
        book.close()
