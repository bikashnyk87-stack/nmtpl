"""Regression of all 5 uploaded client workbook contracts, including dynamic parties."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from openpyxl import load_workbook
from app.services.tiom_despatch_client_layout import (
    DESTINATION_BUCKETS, report_destination_buckets,
    report_destination_bucket_index,
)
from app.services.tiom_despatch_client_reports import build_client_workbook


def trip(epass,day,buyer="Self",destination="Dabuna",grade="S.Fines(60-62)",
         transporter="RIDHICON LOGISTICS PRIVATE LIMITED",status="ACTIVE"):
    return SimpleNamespace(epass_no=epass,report_date=day,permit_no=epass.split("/")[0],
        permit_qty=Decimal("4000"),buyer=buyer,destination=destination,material_grade=grade,
        vehicle_no="OD09AA1234",transporter=transporter,
        net_mt=Decimal("30.125"),tare_mt=Decimal("15.250"),gross_mt=Decimal("45.375"),
        stack_no="J26085113340",consignee="SOURCE REFERENCE",dispatch_time="12:00:00",
        status=status,source="GMAIL XLS")


def data():
    # Existing uploaded client buckets stay in their original positions.
    # A previously unseen customer and transporter are introduced together.
    return [
        trip("L102600001/1",date(2026,11,2)),
        trip("L102699999/1",date(2026,11,2),"NEW CUSTOMER PRIVATE LIMITED",
             "NEW RAIL SIDING", "S.Fines(60-62)", "NEW ROADLINES COMPANY"),
    ]


def test_bucket_adds_new_customer_without_changing_original_45_columns():
    rows=data()
    categories=report_destination_buckets(rows)
    assert categories[:len(DESTINATION_BUCKETS)]==DESTINATION_BUCKETS
    assert len(categories)==len(DESTINATION_BUCKETS)+1
    assert categories[-1]==("NEW CUSTOMER PRIVATE LIMITED","NEW RAIL SIDING","S.Fines(60-62)")
    assert report_destination_bucket_index(rows[1],categories)==len(DESTINATION_BUCKETS)
    assert report_destination_bucket_index(rows[0],categories)==6


def test_all_five_client_templates_keep_contracts_and_uniform_headings():
    from_date=to_date=date(2026,11,2)
    rows=data()
    for kind in ("trip","transporter","material","destination","despatch"):
        output,_=build_client_workbook(kind,rows,from_date,to_date)
        wb=load_workbook(output,read_only=False)
        try:
            assert wb.worksheets
            assert all(sheet.sheet_view.showGridLines is False for sheet in wb.worksheets)
            if kind=="trip":
                assert wb.sheetnames == ["02.11.26","Cummulative","Cancellation"]
                sheet=wb["02.11.26"]
                assert [sheet.cell(2,c).value for c in range(1,17)]==[
                    "Sl.No.","Permit No.","Permit Qty.","Buyer Name",
                    "E-Pass No","Vehicle RegNo","Transporter Name",
                    "Destination","Material/Grade","Stack No.",
                    "Consignee Name","Tare Wt.","Gross Wt.","Net Wt.","Date ","Time",
                ]
                assert sheet.row_dimensions[2].height>=30
                assert sheet["A3"].value==1
                assert sheet["G4"].value=="NEW ROADLINES COMPANY"
                assert sheet["N4"].value==30.125
            if kind=="material":
                ws=wb["Nov-26"]
                assert "NOVEMBER-2026" in ws["A1"].value
                assert ws["A1"].alignment.horizontal=="center"
                assert ws.row_dimensions[2].height>=40
                assert ws["H2"].value=="S.Fines(60-62)"
                assert ws["O4"].value=="=SUM(B4:N4)"
            if kind=="despatch":
                ws=wb["DESTINATION WISE"]
                assert ws["B2"].value=="DABUNA PLANT"
                assert ws["I2"].value=="NON CAPTIVE"
                assert ws["V2"].value=="CUMMULATIVE"
                assert ws.row_dimensions[3].height>=40
            if kind=="destination":
                ws=wb["Nov-26"]
                new_column=2+2*report_destination_buckets(rows,"destination").index(("NEW CUSTOMER PRIVATE LIMITED","NEW RAIL SIDING","S.Fines(60-62)"))
                assert ws.cell(2,new_column).value=="NEW CUSTOMER PRIVATE LIMITED"
                assert ws.cell(3,new_column).value=="NEW RAIL SIDING"
                assert ws.cell(4,new_column).value=="S.Fines(60-62)"
                assert ws.cell(7,new_column).value==1
                assert ws.cell(7,new_column+1).value==30.125
                assert ws.row_dimensions[2].height>=50
                assert ws.row_dimensions[4].height>=40
                assert ws["A1"].alignment.horizontal=="left"  # visible without scrolling the wide report
            if kind=="transporter":
                ws=wb["02.11.26"]
                assert ws["B2"].value=="AMIPL DISPATCH DETAILS ON DT-02/11/2026"
                assert "F4:J4" in {str(m) for m in ws.merged_cells.ranges}
                assert "L4:P4" in {str(m) for m in ws.merged_cells.ranges}
                assert "B24:B27" in {str(m) for m in ws.merged_cells.ranges}
                assert ws["B28"].value=="RIDHICON LOGISTICS PRIVATE LIMITED"
                assert ws["B29"].value=="NEW ROADLINES COMPANY"
                assert ws["B30"].value=="Grand Total"
                assert ws.row_dimensions[24].height>=50
                assert ws.row_dimensions[26].height>=40
        finally:
            wb.close()


def test_captive_report_extends_verifiable_non_captive_grade_and_keeps_totals():
    day=date(2026,11,3)
    records=[
        trip("L102604962/8",day,"DNA MINERALS PVT LTD",
             "Bongobari(Purulia)","5-18mm(62-65)"),
        trip("L102604962/9",day,"DNA MINERALS PVT LTD",
             "Bongobari(Purulia)","5-18mm(62-65)"),
        trip("L102604962/10",day,"DNA MINERALS PVT LTD",
             "Bongobari(Purulia)","5-18mm(62-65)"),
    ]
    records[0].permit_qty=Decimal("0")
    records[0].dispatch_time=""
    output,summary=build_client_workbook("despatch",records,day,day)
    assert summary["trips"]==3
    wb=load_workbook(output)
    try:
        ws=wb["DESTINATION WISE"]
        assert ws["U3"].value.replace("\n","")=="18-40mm(62-65)"  # original column retained
        assert ws["V3"].value.replace("\n","")=="5-18mm(62-65)"  # new approved grade
        assert ws["W2"].value=="CUMMULATIVE"
        assert ws["V6"].value==90.375
        assert ws["W6"].value=="=SUM(B6:V6)+W5"
        assert ws["W34"].value=="=W33"
    finally:
        wb.close()
    trip_output,_=build_client_workbook("trip",records,day,day)
    trip_wb=load_workbook(trip_output)
    try:
        ws=trip_wb["03.11.26"]
        assert ws["C3"].value is None
        assert ws["P3"].value is None
    finally:
        trip_wb.close()


def test_incomplete_new_party_cannot_be_guessed_from_transporter():
    rec=trip("L102699999/2",date(2026,11,2),"","", "",
             "BRAND NEW TRANSPORT")
    try:
        build_client_workbook("destination",[rec],date(2026,11,2),date(2026,11,2))
    except ValueError as exc:
        assert "unmapped" in str(exc)
    else:
        raise AssertionError("Unverified buyer/grade must not silently get a new report column")


def test_uploaded_templates_keep_their_own_headings_and_total_positions():
    day=date(2026,10,26)
    rows=[trip('CHECK/1',day)]
    for kind,checks in (
        ('destination',{'CJ2':'Total Ex-Mines','CL2':'Grand Total','CN2':'Cummulative'}),
        ('transporter',{'CK24':'Total Trips','CL24':'Total Quantity',
                        'AM25':'Banskopa(WB)','AM26':'5-40mm(58-60)',
                        'AY26':'5-40mm(58-60)','BM26':'5-40mm(55-58)',
                        'BO26':'5-18mm(60-62)','CG26':'5-40mm(60-62)'}),
    ):
        output,_=build_client_workbook(kind,rows,day,day)
        wb=load_workbook(output)
        ws=wb.active
        for address,value in checks.items():
            assert ws[address].value==value, (kind,address,ws[address].value)
        if kind=='destination':
            assert 'OCTOBER-2026' in ws['A1'].value
            assert 'X3:AA3' in {str(x) for x in ws.merged_cells.ranges}
        wb.close()


def test_new_party_save_single_batch_suggestions_and_all_five_exports():
    from sqlalchemy.orm import Session
    from app.routers import tiom_despatch as mod
    from test_tiom_despatch_http_flow import client
    api,engine,old=client()
    try:
        with Session(engine) as db:
            for permit in ('NEWONE','NEWTWO'):
                db.add(mod.DespatchTrip(epass_no=permit+'/1',permit_no=permit,
                    report_date=date(2026,11,2),net_mt=Decimal('30.125'),
                    tare_mt=Decimal('15.25'),gross_mt=Decimal('45.375'),
                    buyer='',destination='',material_grade='',status='ACTIVE',
                    transporter='NEW ROADLINES COMPANY'))
            db.commit()
        def entry(permit):
            return {'permit_no':permit,'buyer':'NEW CUSTOMER PRIVATE LIMITED',
                    'destination':'NEW RAIL SIDING','material':'S.Fines(60-62)',
                    'grade_percent':'60.50','amns_trips':1,'amns_mt':'30.125'}
        response=api.post('/api/tiom/despatch/permit-entry-one',json={
            'report_date':'2026-11-02','permit':entry('NEWONE')})
        assert response.status_code==200,response.text
        response=api.post('/api/tiom/despatch/permit-entry-batch',json={
            'report_date':'2026-11-02','permits':[entry('NEWONE'),entry('NEWTWO')]})
        assert response.status_code==200,response.text
        prefill=api.get('/api/tiom/despatch/permit-entry-prefill?report_date=2026-11-02').json()
        assert 'NEW CUSTOMER PRIVATE LIMITED' in prefill['buyerOptions']
        assert 'NEW RAIL SIDING' in prefill['destinationOptions']
        mapping=api.get('/api/tiom/despatch/mapping-status?report_date=2026-11-02').json()
        assert mapping['unmappedTrips']==0,mapping
        for kind in ('trip','destination','transporter','material','despatch'):
            query='?from_date=2026-11-02&to_date=2026-11-02'
            check=api.get('/api/tiom/despatch/export-check/'+kind+query)
            assert check.json()['ready'],check.text
            exported=api.get('/api/tiom/despatch/export/'+kind+query)
            assert exported.status_code==200,exported.text
            wb=load_workbook(BytesIO(exported.content))
            ws=wb.active
            if kind=='destination':
                cells=[c for c in ws[2] if c.value=='NEW CUSTOMER PRIVATE LIMITED']
                assert len(cells)==1
                assert ws.cell(7,cells[0].column).value==2
                assert ws.cell(7,cells[0].column+1).value==60.25
            if kind=='transporter':
                assert ws['B28'].value=='NEW ROADLINES COMPANY'
                cells=[c for c in ws[24] if c.value=='NEW CUSTOMER PRIVATE LIMITED']
                assert len(cells)==1
                assert ws.cell(28,cells[0].column).value==2
                assert ws.cell(28,cells[0].column+1).value==60.25
            wb.close()
    finally:
        mod.get_user,mod.require,mod.csrf=old
        engine.dispose()
