"""All five Despatch report types must export unfrozen worksheets.

Preserve client-format cells and validate the actual XLSX sheetViews,
including every daily, cumulative and cancellation worksheet.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from openpyxl import load_workbook

from app.services.tiom_despatch_client_reports import build_client_workbook


def trip(epass, day, *, qty=0, status="ACTIVE"):
    return SimpleNamespace(
        epass_no=epass, report_date=day, permit_no=epass.split("/")[0],
        permit_qty=Decimal(str(qty)), buyer="Self", destination="Dabuna",
        material_grade="S.Fines(60-62)", vehicle_no="OD09AA1234",
        transporter="RIDHICON LOGISTICS PRIVATE LIMITED",
        stack_no="J26085113340", consignee="071813056432/AMNS",
        tare_mt=Decimal("15.000"), gross_mt=Decimal("46.125"),
        net_mt=Decimal("31.125"), dispatch_time="11:30:05",
        status=status, source="VERIFIED TEST",
    )


def test_trip_summary_all_three_sheet_views_are_valid_and_qty_is_unmodified():
    rows=[
        trip("L102604966/1",date(2026,11,5),qty="8000.620"),
        trip("L102604966/2",date(2026,11,6),qty="0"),
        trip("L102604966/3",date(2026,11,6),qty="0",status="CANCELLED"),
    ]
    buf,_=build_client_workbook("trip",rows,date(2026,11,6),date(2026,11,6))
    data=buf.getvalue()
    with ZipFile(BytesIO(data)) as zipped:
        sheets=[name for name in zipped.namelist()
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")]
        assert len(sheets)==3
        n={"x":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for xml_name in sheets:
            root=ET.fromstring(zipped.read(xml_name))
            view=root.find("x:sheetViews/x:sheetView",n)
            assert view is not None, xml_name
            assert view.find("x:pane",n) is None, xml_name
            selections=view.findall("x:selection",n)
            assert len(selections)==1, (xml_name,len(selections))
            assert selections[0].get("pane") is None, xml_name
    book=load_workbook(BytesIO(data))
    try:
        assert book.sheetnames==["06.11.26","Cummulative","Cancellation"]
        ws=book["06.11.26"]
        assert ws["C2"].value=="Permit Qty."
        assert ws["C3"].value is None  # no approved quantity on this source row
        assert ws["P3"].value=="11:30:05"
        assert ws.freeze_panes is None
        assert book["Cummulative"]["C3"].value==8000.62  # first row is 5 Nov
        assert book["Cummulative"]["C4"].value is None   # second row is 6 Nov
        assert book["Cummulative"].freeze_panes is None
        assert book["Cancellation"].freeze_panes is None
    finally:
        book.close()


def test_all_five_despatch_reports_have_no_frozen_panes_or_sheetview_pane_xml():
    records=[trip("L102604966/1",date(2026,11,6),qty="8000.620")]
    for kind in ("trip","material","destination","despatch","transporter"):
        buf,_=build_client_workbook(kind,records,date(2026,11,6),date(2026,11,6))
        with ZipFile(BytesIO(buf.getvalue())) as zipped:
            xml_names=[name for name in zipped.namelist()
                       if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")]
            assert xml_names
            n={"x":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for xml_name in xml_names:
                view=ET.fromstring(zipped.read(xml_name)).find("x:sheetViews/x:sheetView",n)
                assert view is not None,(kind,xml_name)
                assert view.find("x:pane",n) is None,(kind,xml_name)
                selections=view.findall("x:selection",n)
                assert len(selections)==1,(kind,xml_name,len(selections))
                assert selections[0].get("pane") is None,(kind,xml_name)
        book=load_workbook(BytesIO(buf.getvalue()))
        try:
            assert book.worksheets
            for ws in book.worksheets:
                assert ws.freeze_panes is None,(kind,ws.title,ws.freeze_panes)
                assert len(ws.sheet_view.selection)==1,(kind,ws.title)
        finally:
            book.close()


def test_missing_quantity_is_reported_once_per_permit_with_mis_navigation():
    js=(Path(__file__).parents[1]/"app"/"static"/"tiom_despatch.js").read_text("utf-8")
    for marker in ("missingQtyPermits","tiomDDOpenPermitQty","dd_pe_qty_",
                   "Enter approved Qty", "qtyOnly:true",
                   "No E-Pass", "Do not substitute dispatched MT"):
        assert marker in js
