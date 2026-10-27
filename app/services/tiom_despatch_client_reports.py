"""Generate October 2026 TIOM despatch reports in original client workbook layouts.

Source templates:
- Trip Summary Oct-26.xlsx
- Transporter wise Dispatch Report_Oct-26.xlsx
- Material Wise Dispatch Repor 2026-27.xlsx (Oct-26)
- Destination Wise Report Oct-26.xlsx (Oct-26)
- Despatch Report Oct-2026.xlsx (DESTINATION WISE)

Data is always sourced from active TIOM despatch E-Pass records. Cancelled records
are visible only in the Trip Summary's Cancellation sheet.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from calendar import monthrange

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as col
from openpyxl.workbook.properties import CalcProperties
from openpyxl.worksheet.page import PageMargins

from app.services.tiom_despatch_client_layout import (
    CAPTIVE_MATERIALS, NON_CAPTIVE_MATERIALS, MATERIAL_COLUMNS,
    DESTINATION_BUCKETS, TRANSPORTERS_26_OCT, normalized,
    classified_material, destination_bucket_index, is_captive,
)

HEADERS = [
    "Sl.No.", "Permit No.", "Permit Qty.", "Buyer Name", "E-Pass No",
    "Vehicle RegNo", "Transporter Name", "Destination", "Material/Grade",
    "Stack No.", "Consignee Name", "Tare Wt.", "Gross Wt.", "Net Wt.",
    "Date ", "Time",
]
BLUE = "184768"
MID = "36769A"
PALE = "E5F1F6"
GREY = "E5E9EB"
DARK = "152936"
WHITE = "FFFFFF"
YELLOW = "FFF1C7"
LINE = Side(style="thin", color="8096A3")
NUM = '#,##0.000'
INT = '#,##0'
DATE = 'DD-MM-YYYY'


def _fmt(ws, last_col=16, landscape=True):
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_margins = PageMargins(left=.2, right=.2, top=.35, bottom=.35,
                                  header=.13, footer=.13)
    ws.freeze_panes = "B3"
    ws.print_options.horizontalCentered = True


def _style(ws, r, c, value=None, header=False, total=False, fmt=None):
    x = ws.cell(r, c)
    if value is not None:
        x.value = value
    if header or total:
        x.font = Font(name="Calibri", size=9, bold=True, color=WHITE if header else DARK)
        x.fill = PatternFill("solid", fgColor=BLUE if header else YELLOW)
        x.border = Border(left=LINE, right=LINE, top=LINE, bottom=LINE)
    else:
        x.font = Font(name="Calibri", size=9, color=DARK)
        x.border = Border(bottom=Side(style="hair", color="C9D3D9"))
    x.alignment = Alignment(vertical="center", horizontal="right" if fmt else "left", wrap_text=header)
    if fmt:
        x.number_format = fmt
    return x


def _title(ws, cell, value, end_col):
    ws.merge_cells(start_row=cell, start_column=1, end_row=cell, end_column=end_col)
    x=ws.cell(cell,1,value)
    x.font=Font(name="Calibri",size=14,bold=True,color=WHITE)
    x.fill=PatternFill("solid",fgColor=BLUE)
    x.alignment=Alignment(horizontal="center",vertical="center")
    ws.row_dimensions[cell].height=27


def _days(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _groups(trips):
    dates = defaultdict(list)
    for x in trips:
        dates[x.report_date].append(x)
    return dates


def _sum(trips):
    return round(sum((Decimal(str(x.net_mt)) for x in trips), Decimal("0")),3)


def _keymap(trips):
    matrix=defaultdict(lambda: [0,Decimal("0")])
    missing=[]
    for trip in trips:
        idx=destination_bucket_index(trip)
        if idx is None:
            missing.append(trip)
        else:
            matrix[(trip.report_date,idx)][0]+=1
            matrix[(trip.report_date,idx)][1]+=Decimal(str(trip.net_mt))
    return matrix,missing


def _material_counts(trips):
    mat=defaultdict(Decimal)
    miss=[]
    available={normalized(x) for x in MATERIAL_COLUMNS}
    for t in trips:
        k=classified_material(t)
        if k not in available:
            miss.append(t)
        else:
            mat[(t.report_date,k)]+=Decimal(str(t.net_mt))
    return mat,miss


def _trip_row(x, index):
    dtext = (x.report_date.strftime("%b %e %Y") if hasattr(x.report_date,"strftime")
             else str(x.report_date))
    return (
        index, x.permit_no, float(x.permit_qty or 0), x.buyer,
        x.epass_no, x.vehicle_no, x.transporter, x.destination,
        x.material_grade, x.stack_no, x.consignee,
        float(x.tare_mt), float(x.gross_mt), float(x.net_mt), dtext.strip(),
        x.dispatch_time,
    )


def _detail_page(ws, trips, cancellation=False):
    _fmt(ws,16)
    ws.freeze_panes="A3"
    ws.sheet_view.zoomScale=85
    ws["A1"]="CANCELLATION DETAILS:-" if cancellation else " "
    ws["M1"]="T.Trips:-"
    ws["N1"]=len(trips)
    ws["O1"]="Total Qty:-"
    ws["P1"]=float(_sum(trips))
    ws["N1"].number_format=INT
    ws["P1"].number_format=NUM
    for j,head in enumerate(HEADERS,1):
        _style(ws,2,j,head,header=True)
    ws.row_dimensions[2].height=30
    sizes=[8,17,15,33,24,18,39,25,25,19,55,12,12,12,18,21]
    for j,width in enumerate(sizes,1):
        ws.column_dimensions[col(j)].width=width
    for i,trip in enumerate(trips,3):
        vals=_trip_row(trip,i-2)
        for j,v in enumerate(vals,1):
            _style(ws,i,j,v,fmt=NUM if j in {3,12,13,14} else None)
    ws.print_title_rows="1:2"
    ws.auto_filter.ref=f"A2:P{max(3,len(trips)+2)}"
    ws.print_area=f"A1:P{max(5,len(trips)+2)}"


def _build_trip(wb,active,cancelled,from_date,to_date):
    per_day=_groups(active)
    for d in _days(from_date,to_date):
        ws=wb.create_sheet(d.strftime("%d.%m.%y"))
        _detail_page(ws,per_day.get(d,[]))
    # Preserve the client's spelling and order.
    ws=wb.create_sheet("Cummulative")
    _detail_page(ws,sorted(active,key=lambda x:(x.report_date,x.epass_no)))
    ws=wb.create_sheet("Cancellation")
    _detail_page(ws,sorted(cancelled,key=lambda x:(x.report_date,x.epass_no)),True)


def _build_material(wb,trips,as_of):
    ws=wb.create_sheet(as_of.strftime("%b-%y"))
    _fmt(ws,15);ws.freeze_panes="B3"
    ws["A1"]=" DISPATCH REPORT FOR THE MONTH OF "+as_of.strftime("%B-%Y").upper()
    ws.merge_cells("A1:O1")
    ws["A1"].font=Font(bold=True,size=13,name="Calibri")
    ws.row_dimensions[1].height=26
    _style(ws,2,1,"Date",header=True)
    for i,material in enumerate(MATERIAL_COLUMNS,2):
        _style(ws,2,i,material,header=True)
    _style(ws,2,15,"Total Dispatch",header=True)
    ws.row_dimensions[2].height=32
    counts,_=_material_counts(trips)
    days=monthrange(as_of.year,as_of.month)[1]
    ws.column_dimensions["A"].width=17
    for j in range(2,16):
        ws.column_dimensions[col(j)].width=17
    for i in range(1,days+1):
        d=date(as_of.year,as_of.month,i)
        r=i+2
        _style(ws,r,1,datetime(d.year,d.month,d.day),fmt=DATE)
        for j,name in enumerate(MATERIAL_COLUMNS,2):
            value=counts[(d,normalized(name))]
            _style(ws,r,j,float(value),fmt=NUM)
        _style(ws,r,15,f"=SUM(B{r}:N{r})",fmt=NUM)
    total_row=days+3
    _style(ws,total_row,1,"Total",total=True)
    for j in range(2,16):
        letter=col(j)
        _style(ws,total_row,j,f"=SUM({letter}3:{letter}{total_row-1})",total=True,fmt=NUM)
    ws.print_area=f"A1:O{total_row}"


def _material_type_head(name):
    return name.replace("(", "\n(").replace(".",".",1)


def _build_captive(wb,trips,as_of):
    ws=wb.create_sheet("DESTINATION WISE")
    _fmt(ws,22);ws.freeze_panes="B4"
    _title(ws,1,"DISPATCH REPORT (CAPTIVE/NON-CAPTIVE) FOR THE MONTH OF "+
           as_of.strftime("%B-%Y").upper(),22)
    ws.merge_cells("A2:A3")
    _style(ws,2,1,"DATE",header=True)
    ws.merge_cells("B2:H2")
    _style(ws,2,2,"DABUNA PLANT",header=True)
    ws.merge_cells("I2:U2")
    _style(ws,2,9,"NON CAPTIVE",header=True)
    ws.merge_cells("V2:V3")
    _style(ws,2,22,"CUMMULATIVE",header=True)
    for i,name in enumerate(CAPTIVE_MATERIALS+NON_CAPTIVE_MATERIALS,2):
        _style(ws,3,i,_material_type_head(name),header=True)
    ws.row_dimensions[3].height=44
    ws.column_dimensions["A"].width=16
    for j in range(2,23):
        ws.column_dimensions[col(j)].width=17
    sums=defaultdict(Decimal)
    miss=[]
    captive={normalized(x):i for i,x in enumerate(CAPTIVE_MATERIALS,2)}
    noncaptive={normalized(x):i for i,x in enumerate(NON_CAPTIVE_MATERIALS,9)}
    for t in trips:
        mat=classified_material(t)
        idx=(captive if is_captive(t) else noncaptive).get(mat)
        if idx is None:
            miss.append(t)
            continue
        sums[(t.report_date,idx)]+=Decimal(str(t.net_mt))
    days=monthrange(as_of.year,as_of.month)[1]
    for i in range(1,days+1):
        d=date(as_of.year,as_of.month,i);r=i+3
        _style(ws,r,1,datetime(d.year,d.month,d.day),fmt=DATE)
        for j in range(2,22):
            _style(ws,r,j,float(sums[(d,j)]),fmt=NUM)
        _style(ws,r,22,f"=SUM(B{r}:U{r})"+(f"+V{r-1}" if i>1 else ""),fmt=NUM)
    last=days+4
    _style(ws,last,1,"TOTAL",total=True)
    for j in range(2,23):
        letter=col(j)
        formula=(f"=V{last-1}" if j==22 else f"=SUM({letter}4:{letter}{last-1})")
        _style(ws,last,j,formula,total=True,fmt=NUM)
    ws.print_area=f"A1:V{last}"
    return miss


def _display_customer(buyer):
    return "SNN MINERALS" if normalized(buyer) == normalized("S N N MINERALS PRIVATE LIMITED.") else buyer


def _build_destination(wb,trips,as_of,matrix):
    ws=wb.create_sheet(as_of.strftime("%b-%y"))
    _fmt(ws,92);ws.freeze_panes="B6";ws.sheet_view.zoomScale=60
    ws.merge_cells("A1:CN1")
    x=ws["A1"]
    x.value="THAKURANI IRON ORE MINE OF M/s ARCELORMITTAL INDIA PRIVATE LTD. ( DESTINATION WISE DISPATCH REPORT )"
    x.font=Font(bold=True,name="Calibri",size=13,color=WHITE)
    x.fill=PatternFill("solid",fgColor=BLUE)
    ws.row_dimensions[1].height=28
    ws.merge_cells("A2:A5")
    _style(ws,2,1,"DATE",header=True)
    ws.column_dimensions["A"].width=18

    # Customer and destination merged ranges exactly follow the uploaded hierarchy;
    # every two adjacent columns represent Trips and Quantity.
    prev_buyer=None;prev_dest=None;buyer_start=2;dest_start=2
    for i,(buyer,dest,grade) in enumerate(DESTINATION_BUCKETS):
        c=2+2*i
        if buyer != prev_buyer:
            if prev_buyer is not None and c-1>buyer_start:
                ws.merge_cells(start_row=2,start_column=buyer_start,end_row=2,end_column=c-1)
            buyer_start=c
            _style(ws,2,c,buyer,header=True)
            prev_buyer=buyer
            prev_dest=None
        if dest != prev_dest:
            if prev_dest is not None and c-1>dest_start:
                ws.merge_cells(start_row=3,start_column=dest_start,end_row=3,end_column=c-1)
            dest_start=c
            _style(ws,3,c,dest,header=True)
            prev_dest=dest
        ws.merge_cells(start_row=4,start_column=c,end_row=4,end_column=c+1)
        _style(ws,4,c,grade,header=True)
        _style(ws,5,c,"Trips",header=True)
        _style(ws,5,c+1,"Quantity",header=True)
        ws.column_dimensions[col(c)].width=11
        ws.column_dimensions[col(c+1)].width=15
    endc=2+len(DESTINATION_BUCKETS)*2
    if endc-1>buyer_start:
        ws.merge_cells(start_row=2,start_column=buyer_start,end_row=2,end_column=endc-1)
    if endc-1>dest_start:
        ws.merge_cells(start_row=3,start_column=dest_start,end_row=3,end_column=endc-1)
    # Original totals after the 43 bucket pairs: CJ/CK, CL/CM and CN.
    for c,head in [(88,"Total Ex-Mines"),(90,"Grand Total"),(92,"Cummulative")]:
        ws.merge_cells(start_row=2,start_column=c,end_row=4,end_column=c+(0 if c==92 else 1))
        _style(ws,2,c,head,header=True)
    for c in (88,90):
        _style(ws,5,c,"TRIP",header=True)
        _style(ws,5,c+1,"QUANTITY",header=True)
    for c in range(88,93):ws.column_dimensions[col(c)].width=17
    ws.row_dimensions[4].height=35
    per_day=_groups(trips)
    days=monthrange(as_of.year,as_of.month)[1]
    for i in range(1,days+1):
        d=date(as_of.year,as_of.month,i);r=i+5
        _style(ws,r,1,datetime(d.year,d.month,d.day),fmt=DATE)
        for idx in range(len(DESTINATION_BUCKETS)):
            c=2+2*idx;count,mt=matrix[(d,idx)]
            _style(ws,r,c,count,fmt=INT)
            _style(ws,r,c+1,float(mt),fmt=NUM)
        _style(ws,r,88,f"=SUM({','.join(col(2+2*j)+str(r) for j in range(9,len(DESTINATION_BUCKETS)))})",fmt=INT)
        _style(ws,r,89,f"=SUM({','.join(col(3+2*j)+str(r) for j in range(9,len(DESTINATION_BUCKETS)))})",fmt=NUM)
        _style(ws,r,90,f"=SUM({','.join(col(2+2*j)+str(r) for j in range(9))})+CJ{r}",fmt=INT)
        _style(ws,r,91,f"=SUM({','.join(col(3+2*j)+str(r) for j in range(9))})+CK{r}",fmt=NUM)
        _style(ws,r,92,f"=CM{r}"+(f"+CN{r-1}" if i>1 else ""),fmt=NUM)
    last=days+6
    _style(ws,last,1,"Total",total=True)
    for c in range(2,93):
        cl=col(c)
        _style(ws,last,c,f"=SUM({cl}6:{cl}{last-1})" if c!=92 else f"=CN{last-1}",total=True,fmt=INT if c%2==0 and c<92 else NUM)
    ws.print_area=f"A1:CN{last}"


def _transporter_grade(index, default):
    # Transporter matrix is an older version of client headings. Preserve
    # its original 5-40mm legend even where Oct material sheet says 5-18mm.
    if 28 <= index <= 36 and default.startswith("5-18mm"):
        return default.replace("5-18mm","5-40mm")
    return default


def _build_transporter(wb,trips,from_date,to_date,matrix):
    day_groups=_groups(trips)
    # Existing transporter names from source sheet 26 Oct, plus any new names.
    traders=sorted({x.transporter for x in trips},
                   key=lambda name:(name not in TRANSPORTERS_26_OCT,
                                    TRANSPORTERS_26_OCT.index(name) if name in TRANSPORTERS_26_OCT else name))
    days=list(_days(from_date,to_date))
    for day in days:
        ws=wb.create_sheet(day.strftime("%d.%m.%y"))
        _fmt(ws,90);ws.sheet_view.zoomScale=55;ws.freeze_panes="C28"
        ws.merge_cells("B2:P2")
        x=ws["B2"]
        x.value="AMIPL DISPATCH DETAILS ON DT-"+day.strftime("%d/%m/%Y")
        x.font=Font(size=14,bold=True,name="Calibri",color=BLUE)
        ws.row_dimensions[2].height=26
        _style(ws,4,6,"DESTINATION WISE DISPATCH",header=True)
        _style(ws,4,12,"MATERIAL WISE DISPATCH",header=True)
        for c,t in [(7,"FTD"),(9,"FTM"),(13,"FTD"),(15,"FTM")]:
            _style(ws,5,c,t,header=True)
        for c,t in [(7,"Trips"),(8,"Quantity"),(9,"Trips"),(10,"Quantity"),
                    (13,"Trips"),(14,"Quantity"),(15,"Trips"),(16,"Quantity")]:
            _style(ws,6,c,t,header=True)
        today=day_groups.get(day,[])
        mtd=[x for x in trips if x.report_date<=day and x.report_date.month==day.month and x.report_date.year==day.year]
        ex_today=[x for x in today if not is_captive(x)]
        ex_mtd=[x for x in mtd if not is_captive(x)]
        self_today=[x for x in today if is_captive(x)]
        self_mtd=[x for x in mtd if is_captive(x)]
        for r,name,ftd,ftm in [
            (7,"Dabuna",self_today,self_mtd),(8,"Ex-mines",ex_today,ex_mtd),
            (9,"Total",today,mtd)]:
            _style(ws,r,6,name,total=(r==9))
            for c,val,fmt in [(7,len(ftd),INT),(8,float(_sum(ftd)),NUM),
                              (9,len(ftm),INT),(10,float(_sum(ftm)),NUM)]:
                _style(ws,r,c,val,total=(r==9),fmt=fmt)
        _style(ws,9,2,"DISPATCH FOR THE DAY :",total=True)
        _style(ws,9,3,len(today),total=True,fmt=INT)
        _style(ws,9,4,float(_sum(today)),total=True,fmt=NUM)
        _style(ws,10,2,"CUMULATIVE FTM            :",total=True)
        _style(ws,10,3,len(mtd),total=True,fmt=INT)
        _style(ws,10,4,float(_sum(mtd)),total=True,fmt=NUM)
        grades=MATERIAL_COLUMNS
        for i,name in enumerate(grades):
            r=i+7
            _style(ws,r,12,name,header=(r==7))
            now=[x for x in today if classified_material(x)==normalized(name)]
            cum=[x for x in mtd if classified_material(x)==normalized(name)]
            for c,v,fmt in [(13,len(now),INT),(14,float(_sum(now)),NUM),
                            (15,len(cum),INT),(16,float(_sum(cum)),NUM)]:
                _style(ws,r,c,v,fmt=fmt)
        _style(ws,20,12,"Total",total=True)
        for c,v,fmt in [(13,len(today),INT),(14,float(_sum(today)),NUM),
                        (15,len(mtd),INT),(16,float(_sum(mtd)),NUM)]:
            _style(ws,20,c,v,total=True,fmt=fmt)
        _style(ws,23,2,"DISPATCH FOR THE DAY",header=True)
        _style(ws,24,2,"TRANSPORTER NAME",header=True)
        prev_buyer=None;prev_dest=None;bstart=3;dstart=3
        for idx,(buyer,dest,grade) in enumerate(DESTINATION_BUCKETS):
            c=3+2*idx
            if buyer != prev_buyer:
                if prev_buyer is not None and c-1>bstart:
                    ws.merge_cells(start_row=24,start_column=bstart,end_row=24,end_column=c-1)
                bstart=c
                _style(ws,24,c,buyer,header=True)
                prev_buyer=buyer;prev_dest=None
            if dest != prev_dest:
                if prev_dest is not None and c-1>dstart:
                    ws.merge_cells(start_row=25,start_column=dstart,end_row=25,end_column=c-1)
                dstart=c
                _style(ws,25,c,dest,header=True)
                prev_dest=dest
            ws.merge_cells(start_row=26,start_column=c,end_row=26,end_column=c+1)
            _style(ws,26,c,_transporter_grade(idx,grade),header=True)
            _style(ws,27,c,"Trips",header=True)
            _style(ws,27,c+1,"Quantity",header=True)
            ws.column_dimensions[col(c)].width=11
            ws.column_dimensions[col(c+1)].width=16
        endc=3+2*len(DESTINATION_BUCKETS)
        if endc-1>bstart:ws.merge_cells(start_row=24,start_column=bstart,end_row=24,end_column=endc-1)
        if endc-1>dstart:ws.merge_cells(start_row=25,start_column=dstart,end_row=25,end_column=endc-1)
        _style(ws,24,89,"Total Trips",header=True)
        _style(ws,24,90,"Total Quantity",header=True)
        ws.column_dimensions["B"].width=42
        ws.column_dimensions["C"].width=17
        ws.column_dimensions["D"].width=16
        for c in range(5,17):ws.column_dimensions[col(c)].width=18
        row_total=28+len(traders)
        per_name=defaultdict(lambda: [0,Decimal("0")])
        for trip in today:
            idx=destination_bucket_index(trip)
            if idx is not None:
                per_name[(normalized(trip.transporter),idx)][0]+=1
                per_name[(normalized(trip.transporter),idx)][1]+=Decimal(str(trip.net_mt))
        for pos,transport in enumerate(traders):
            r=28+pos
            _style(ws,r,2,transport)
            for idx in range(len(DESTINATION_BUCKETS)):
                c=3+2*idx
                count,mt=per_name[(normalized(transport),idx)]
                _style(ws,r,c,count,fmt=INT)
                _style(ws,r,c+1,float(mt),fmt=NUM)
            _style(ws,r,89,f"=SUM({','.join(col(3+2*j)+str(r) for j in range(len(DESTINATION_BUCKETS)))})",fmt=INT)
            _style(ws,r,90,f"=SUM({','.join(col(4+2*j)+str(r) for j in range(len(DESTINATION_BUCKETS)))})",fmt=NUM)
        _style(ws,row_total,2,"Grand Total",total=True)
        for c in range(3,91):
            letter=col(c)
            _style(ws,row_total,c,f"=SUM({letter}28:{letter}{row_total-1})",total=True,
                   fmt=INT if c%2 else NUM)
        ws.print_area=f"B2:CL{row_total}"


def build_client_workbook(report_type, all_records, from_date, to_date):
    """Return (xlsx buffer, counts).

    all_records must include active and cancelled rows from the first of the
    target month through to_date. Handles day-only as well as MTD selection.
    """
    if from_date.month != to_date.month or from_date.year != to_date.year:
        raise ValueError("Export one client-report calendar month at a time")
    if from_date > to_date:
        raise ValueError("Invalid date range")
    in_month=[x for x in all_records if x.report_date.year==to_date.year
              and x.report_date.month==to_date.month and x.report_date<=to_date]
    active=[x for x in in_month if x.status=="ACTIVE"]
    cancelled=[x for x in in_month if x.status=="CANCELLED"]
    if not active:
        raise ValueError("No active E-Pass despatch data exists for this month; import source data first")
    matrix,unmapped=_keymap(active)
    _,material_unmapped=_material_counts(active)
    if report_type in {"destination","transporter"} and unmapped:
        sample=", ".join(x.epass_no for x in unmapped[:5])
        raise ValueError(f"{len(unmapped)} E-Pass movements have unmapped buyer/destination/material buckets: {sample}. Correct aliases before client export.")
    if report_type in {"material","despatch","transporter"} and material_unmapped:
        sample=", ".join(x.epass_no for x in material_unmapped[:5])
        raise ValueError(f"{len(material_unmapped)} E-Pass movements have unknown material grade: {sample}. Verify source before client export.")
    wb=Workbook()
    wb.remove(wb.active)
    wb.calculation=CalcProperties(calcMode="auto",fullCalcOnLoad=True,forceFullCalc=True)
    if report_type=="trip":
        _build_trip(wb,active,cancelled,from_date,to_date)
    elif report_type=="transporter":
        _build_transporter(wb,active,from_date,to_date,matrix)
    elif report_type=="material":
        _build_material(wb,active,to_date)
    elif report_type=="destination":
        _build_destination(wb,active,to_date,matrix)
    elif report_type=="despatch":
        missing=_build_captive(wb,active,to_date)
        if missing:
            sample=", ".join(x.epass_no for x in missing[:5])
            raise ValueError(f"{len(missing)} movements not classified captive/non-captive: {sample}")
    else:
        raise ValueError("Unknown client report type")
    buf=BytesIO()
    wb.save(buf);buf.seek(0)
    return buf, {"trips":len(active), "quantityMt":float(_sum(active)),
                 "dailyTrips":len([x for x in active if x.report_date==to_date]),
                 "dailyQuantityMt":float(_sum([x for x in active if x.report_date==to_date]))}
