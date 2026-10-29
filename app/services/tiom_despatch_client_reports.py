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
from html import unescape
from io import BytesIO
from calendar import monthrange
from functools import lru_cache

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.drawing.image import Image as ExcelImage
from pathlib import Path
from base64 import b64decode
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
DATA_BORDER = Border(left=Side(style="hair", color="CBD7DF"), right=Side(style="hair", color="CBD7DF"),
                     top=Side(style="hair", color="E5EDF2"), bottom=Side(style="hair", color="CBD7DF"))
STRIPE = PatternFill("solid", fgColor="F2F8FB")
NUM = '#,##0.000;-#,##0.000;"";@'  # Blank DISPLAY for zero, numeric value remains 0
INT = '#,##0;-#,##0;"";@'
DATE = 'DD-MM-YYYY'



@lru_cache(maxsize=1)
def _client_logo_bytes():
    asset = Path(__file__).resolve().parents[1] / "static" / "amns_reference_logo.b64"
    return b64decode(asset.read_text(encoding="ascii").strip())


def _client_logo(ws, anchor):
    """Embed the original logo with a shared, cached image payload."""
    logo = ExcelImage(BytesIO(_client_logo_bytes()))
    logo.width, logo.height = 105, 63
    ws.add_image(logo, anchor)



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
    # Printed company wordmark and consistent footer on all client reports.
    ws.oddHeader.left.text = "&BNMTPL | TIOM&B"
    ws.oddHeader.right.text = "DESPATCH REPORT"
    ws.oddFooter.left.text = "Source: Verified E-Pass register"
    ws.oddFooter.right.text = "Page &P of &N"


# Reusing immutable style objects prevents allocations for every cell of the
# 90-column daily transporter workbook while keeping the exact visual layout.
_HEADER_FONT = Font(name="Calibri", size=9, bold=True, color=WHITE)
_TOTAL_FONT = Font(name="Calibri", size=9, bold=True, color=DARK)
_BODY_FONT = Font(name="Calibri", size=9, color=DARK)
_HEADER_FILL = PatternFill("solid", fgColor=BLUE)
_TOTAL_FILL = PatternFill("solid", fgColor=YELLOW)
_HEADER_BORDER = Border(left=LINE, right=LINE, top=LINE, bottom=LINE)
_ALIGN_HEADER = Alignment(vertical="center", horizontal="left", wrap_text=True)
_ALIGN_TEXT = Alignment(vertical="center", horizontal="left", wrap_text=False)
_ALIGN_NUM = Alignment(vertical="center", horizontal="right", wrap_text=False)


def _style(ws, r, c, value=None, header=False, total=False, fmt=None):
    x = ws.cell(r, c)
    if value is not None:
        x.value = value
    if header:
        x.font, x.fill, x.border = _HEADER_FONT, _HEADER_FILL, _HEADER_BORDER
    elif total:
        x.font, x.fill, x.border = _TOTAL_FONT, _TOTAL_FILL, _HEADER_BORDER
    else:
        x.font, x.border = _BODY_FONT, DATA_BORDER
        if r % 2 == 0:
            x.fill = STRIPE
    x.alignment = _ALIGN_HEADER if header else (_ALIGN_NUM if fmt else _ALIGN_TEXT)
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
    for a in ("M1","N1","O1","P1"):
        ws[a].fill = PatternFill("solid", fgColor=PALE)
        ws[a].font = Font(name="Calibri",size=10,bold=True,color=BLUE)
        ws[a].border = DATA_BORDER
    for j,head in enumerate(HEADERS,1):
        _style(ws,2,j,head,header=True)
    ws.row_dimensions[2].height=30
    sizes=[8,17,15,33,24,18,39,25,25,19,55,12,12,12,18,21]
    for j,width in enumerate(sizes,1):
        ws.column_dimensions[col(j)].width=width
    # Thousands of trip records are present twice (daily + cumulative).
    # Keep original values/number formats but bulk-append data rows: constructing
    # 16 new Font, Border and Alignment objects PER TRIP was the main slowdown.
    for i, trip in enumerate(trips, 1):
        ws.append(_trip_row(trip, i))
    for row in ws.iter_rows(min_row=3, max_row=len(trips)+2,
                            min_col=1, max_col=16):
        for c in row:
            c.border = DATA_BORDER
            if c.row % 2 == 0:
                c.fill = STRIPE
            if c.column in (3, 12, 13, 14):
                c.number_format=NUM
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
    category_end = 2 + 2*len(DESTINATION_BUCKETS)
    ex_col, total_col, cumulative_col = category_end, category_end+2, category_end+4
    _fmt(ws,cumulative_col);ws.freeze_panes="B6";ws.sheet_view.zoomScale=60
    ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=cumulative_col)
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
    # Totals follow the original category columns plus any newly approved
    # AMNS source destinations. Never merge Saraikela into Chandil.
    for c,head in [(ex_col,"Total Ex-Mines"),(total_col,"Grand Total"),
                   (cumulative_col,"Cummulative")]:
        ws.merge_cells(start_row=2,start_column=c,end_row=4,
                       end_column=c+(0 if c==cumulative_col else 1))
        _style(ws,2,c,head,header=True)
    for c in (ex_col,total_col):
        _style(ws,5,c,"TRIP",header=True)
        _style(ws,5,c+1,"QUANTITY",header=True)
    for c in range(ex_col,cumulative_col+1):ws.column_dimensions[col(c)].width=17
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
        _style(ws,r,ex_col,f"=SUM({','.join(col(2+2*j)+str(r) for j in range(9,len(DESTINATION_BUCKETS)))})",fmt=INT)
        _style(ws,r,ex_col+1,f"=SUM({','.join(col(3+2*j)+str(r) for j in range(9,len(DESTINATION_BUCKETS)))})",fmt=NUM)
        _style(ws,r,total_col,f"=SUM({','.join(col(2+2*j)+str(r) for j in range(9))})+{col(ex_col)}{r}",fmt=INT)
        _style(ws,r,total_col+1,f"=SUM({','.join(col(3+2*j)+str(r) for j in range(9))})+{col(ex_col+1)}{r}",fmt=NUM)
        _style(ws,r,cumulative_col,f"={col(total_col+1)}{r}"+(f"+{col(cumulative_col)}{r-1}" if i>1 else ""),fmt=NUM)
    last=days+6
    _style(ws,last,1,"Total",total=True)
    for c in range(2,cumulative_col+1):
        cl=col(c)
        _style(ws,last,c,f"=SUM({cl}6:{cl}{last-1})"
               if c != cumulative_col else f"={cl}{last-1}",
               total=True,fmt=INT if c%2==0 and c<cumulative_col else NUM)
    ws.print_area=f"A1:{col(cumulative_col)}{last}"


def _transporter_grade(index, default):
    # Transporter matrix is an older version of client headings. Preserve
    # its original 5-40mm legend even where Oct material sheet says 5-18mm.
    if 28 <= index <= 36 and default.startswith("5-18mm"):
        return default.replace("5-18mm","5-40mm")
    return default


def _transporter_names(trips):
    """One display name per entity, including HTML-escaped, spacing and case variants.

    E-pass rows remain unchanged. Only the client export's display groups are
    consolidated, so no underlying trips or their quantities are duplicated.
    """
    official = {normalized(name): name.strip() for name in TRANSPORTERS_26_OCT}
    names = {}
    for trip in trips:
        original = " ".join(unescape(str(trip.transporter or "")).split())
        key = normalized(original)
        if not key:
            key = "(unnamed transporter)"
            original = "Unspecified transporter"
        if key not in names:
            names[key] = official.get(key, original)
    order = {normalized(value): i for i, value in enumerate(TRANSPORTERS_26_OCT)}
    return sorted(names.items(), key=lambda x: (
        order.get(x[0], len(order)), x[1].casefold()
    ))


def _build_transporter(wb,trips,from_date,to_date,matrix):
    # Pre-aggregate E-Passes once. Previously every day recalculated its
    # month-to-date totals and each of 13 material grades by rescanning all
    # E-Passes, yielding O(days * grades * trips) work.
    traders = _transporter_names(trips)
    days = list(_days(from_date, to_date))
    daily_totals = defaultdict(lambda: [0, Decimal("0")])
    daily_captive = defaultdict(lambda: [0, Decimal("0")])
    daily_material = defaultdict(lambda: [0, Decimal("0")])
    daily_transporter = defaultdict(lambda: [0, Decimal("0")])
    for trip in trips:
        d = trip.report_date
        weight = Decimal(str(trip.net_mt))
        daily_totals[d][0] += 1
        daily_totals[d][1] += weight
        if is_captive(trip):
            daily_captive[d][0] += 1
            daily_captive[d][1] += weight
        grade = classified_material(trip)
        daily_material[(d, grade)][0] += 1
        daily_material[(d, grade)][1] += weight
        idx = destination_bucket_index(trip)
        if idx is not None:
            key = (d, normalized(trip.transporter), idx)
            daily_transporter[key][0] += 1
            daily_transporter[key][1] += weight

    # Include the first of the month even for a one-day export: FTM remains
    # month-to-date, never limited to the currently selected daily sheet.
    rolling_total = [0, Decimal("0")]
    rolling_captive = [0, Decimal("0")]
    rolling_material = defaultdict(lambda: [0, Decimal("0")])
    totals_to_day = {}
    for d in _days(to_date.replace(day=1), to_date):
        for running, daily in ((rolling_total, daily_totals[d]),
                               (rolling_captive, daily_captive[d])):
            running[0] += daily[0]
            running[1] += daily[1]
        for grade in MATERIAL_COLUMNS:
            key = normalized(grade)
            current = daily_material[(d, key)]
            running = rolling_material[key]
            running[0] += current[0]
            running[1] += current[1]
        totals_to_day[d] = (
            tuple(rolling_total), tuple(rolling_captive),
            {key: tuple(value) for key, value in rolling_material.items()},
        )
    # Prefix sums of per-date transporter totals, so the source-approved
    # cumulative table is produced on EACH daily worksheet without rescans.
    transport_per_day = defaultdict(list)
    for (d, transport_key, idx), count_mt in daily_transporter.items():
        transport_per_day[d].append((transport_key, idx, count_mt))
    running_transport = defaultdict(lambda: [0, Decimal("0")])
    day_to_transporter = {}
    report_days = set(days)
    for d in _days(to_date.replace(day=1), to_date):
        for transport_key, idx, val in transport_per_day[d]:
            tally = running_transport[(transport_key, idx)]
            tally[0] += val[0]
            tally[1] += val[1]
        if d in report_days:
            day_to_transporter[d] = {k: tuple(v) for k,v in running_transport.items()}
    for day in days:
        ws=wb.create_sheet(day.strftime("%d.%m.%y"))
        _fmt(ws,90);ws.sheet_view.zoomScale=55;ws.freeze_panes="C28"
        ws.merge_cells("B1:E1")
        mark=ws["B1"]
        mark.value="NMTPL  |  TIOM DESPATCH"
        mark.font=Font(name="Calibri",size=12,bold=True,color=WHITE)
        mark.fill=PatternFill("solid",fgColor=BLUE)
        mark.alignment=Alignment(horizontal="center",vertical="center")
        ws.row_dimensions[1].height=23
        _client_logo(ws, "Q1")
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
        today_total = daily_totals[day]
        today_self = daily_captive[day]
        mtd_total, mtd_self, mtd_grades = totals_to_day[day]
        today_other = (today_total[0]-today_self[0], today_total[1]-today_self[1])
        mtd_other = (mtd_total[0]-mtd_self[0], mtd_total[1]-mtd_self[1])
        for r,name,ftd,ftm in [
            (7,"Dabuna",today_self,mtd_self),(8,"Ex-mines",today_other,mtd_other),
            (9,"Total",today_total,mtd_total)]:
            _style(ws,r,6,name,total=(r==9))
            for c,val,fmt in [(7,ftd[0],INT),(8,float(round(ftd[1],3)),NUM),
                              (9,ftm[0],INT),(10,float(round(ftm[1],3)),NUM)]:
                _style(ws,r,c,val,total=(r==9),fmt=fmt)
        _style(ws,9,2,"DISPATCH FOR THE DAY :",total=True)
        _style(ws,9,3,today_total[0],total=True,fmt=INT)
        _style(ws,9,4,float(round(today_total[1],3)),total=True,fmt=NUM)
        _style(ws,10,2,"CUMULATIVE FTM            :",total=True)
        _style(ws,10,3,mtd_total[0],total=True,fmt=INT)
        _style(ws,10,4,float(round(mtd_total[1],3)),total=True,fmt=NUM)
        for i,name in enumerate(MATERIAL_COLUMNS):
            r=i+7
            _style(ws,r,12,name,header=(r==7))
            key = normalized(name)
            now = daily_material[(day,key)]
            cum = mtd_grades[key]
            for c,v,fmt in [(13,now[0],INT),(14,float(round(now[1],3)),NUM),
                            (15,cum[0],INT),(16,float(round(cum[1],3)),NUM)]:
                _style(ws,r,c,v,fmt=fmt)
        _style(ws,20,12,"Total",total=True)
        for c,v,fmt in [(13,today_total[0],INT),(14,float(round(today_total[1],3)),NUM),
                        (15,mtd_total[0],INT),(16,float(round(mtd_total[1],3)),NUM)]:
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
        total_trips_col=3+2*len(DESTINATION_BUCKETS)
        total_mt_col=total_trips_col+1
        _style(ws,24,total_trips_col,"Total Trips",header=True)
        _style(ws,24,total_mt_col,"Total Quantity",header=True)
        ws.column_dimensions["B"].width=42
        ws.column_dimensions["C"].width=17
        ws.column_dimensions["D"].width=16
        for c in range(5,17):ws.column_dimensions[col(c)].width=18
        row_total=28+len(traders)
        for pos,(transport_key, display_name) in enumerate(traders):
            r=28+pos
            _style(ws,r,2,display_name)
            for idx in range(len(DESTINATION_BUCKETS)):
                c=3+2*idx
                count,mt=daily_transporter[(day,transport_key,idx)]
                _style(ws,r,c,count,fmt=INT)
                _style(ws,r,c+1,float(mt),fmt=NUM)
            _style(ws,r,total_trips_col,f"=SUM({','.join(col(3+2*j)+str(r) for j in range(len(DESTINATION_BUCKETS)))})",fmt=INT)
            _style(ws,r,total_mt_col,f"=SUM({','.join(col(4+2*j)+str(r) for j in range(len(DESTINATION_BUCKETS)))})",fmt=NUM)
        _style(ws,row_total,2,"Grand Total",total=True)
        for c in range(3,total_mt_col+1):
            letter=col(c)
            _style(ws,row_total,c,f"=SUM({letter}28:{letter}{row_total-1})",total=True,
                   fmt=INT if c%2 else NUM)
        _append_transporter_cumulative(
            ws, day, traders, day_to_transporter[day],
            start_row=row_total+2,
        )


def _append_transporter_cumulative(ws, as_of, transporters, cumulative, start_row):
    """Same-sheet cumulative table immediately below daily transporter total."""
    blue_line = Side(style="thin", color="253542")
    peach = PatternFill("solid", fgColor="F5C7A0")
    label_row = start_row
    buyer_row, dest_row, grade_row, trip_row = (
        start_row+1, start_row+2, start_row+3, start_row+4
    )
    first = start_row+5
    total_trips_col=3+2*len(DESTINATION_BUCKETS)
    total_mt_col=total_trips_col+1
    ws.merge_cells(start_row=label_row, start_column=2,
                   end_row=label_row, end_column=total_mt_col)
    title = ws.cell(label_row,2)
    title.value = ("CUMULATIVE DISPATCH FOR THE MONTH OF "
                   + as_of.strftime("%B-%Y").upper())
    title.font = Font(name="Calibri",size=12,bold=True,color=DARK)
    title.fill = peach
    title.border = Border(top=blue_line,bottom=blue_line)
    title.alignment = Alignment(horizontal="left",vertical="center")
    ws.row_dimensions[label_row].height=25
    ws.merge_cells(start_row=buyer_row,start_column=2,
                   end_row=trip_row,end_column=2)
    _style(ws,buyer_row,2,"TRANSPORTER NAME",header=True)
    previous_buyer = previous_dest = None
    buyer_start = dest_start = 3
    for idx,(buyer,dest,grade) in enumerate(DESTINATION_BUCKETS):
        c=3+2*idx
        if buyer!=previous_buyer:
            if previous_buyer is not None and c-1>buyer_start:
                ws.merge_cells(start_row=buyer_row,start_column=buyer_start,
                               end_row=buyer_row,end_column=c-1)
            buyer_start=c
            _style(ws,buyer_row,c,buyer,header=True)
            previous_buyer,previous_dest=buyer,None
        if dest!=previous_dest:
            if previous_dest is not None and c-1>dest_start:
                ws.merge_cells(start_row=dest_row,start_column=dest_start,
                               end_row=dest_row,end_column=c-1)
            dest_start=c
            _style(ws,dest_row,c,dest,header=True)
            previous_dest=dest
        ws.merge_cells(start_row=grade_row,start_column=c,
                       end_row=grade_row,end_column=c+1)
        _style(ws,grade_row,c,_transporter_grade(idx,grade),header=True)
        _style(ws,trip_row,c,"Trips",header=True)
        _style(ws,trip_row,c+1,"Quantity",header=True)
    if total_trips_col-1>buyer_start:
        ws.merge_cells(start_row=buyer_row,start_column=buyer_start,
                       end_row=buyer_row,end_column=total_trips_col-1)
    if total_trips_col-1>dest_start:
        ws.merge_cells(start_row=dest_row,start_column=dest_start,
                       end_row=dest_row,end_column=total_trips_col-1)
    ws.merge_cells(start_row=buyer_row,start_column=total_trips_col,
                   end_row=trip_row,end_column=total_trips_col)
    ws.merge_cells(start_row=buyer_row,start_column=total_mt_col,
                   end_row=trip_row,end_column=total_mt_col)
    _style(ws,buyer_row,total_trips_col,"Total Trips",header=True)
    _style(ws,buyer_row,total_mt_col,"Total Quantity",header=True)
    for i,(transport_key,display_name) in enumerate(transporters):
        row=first+i
        _style(ws,row,2,display_name)
        for idx in range(len(DESTINATION_BUCKETS)):
            c=3+2*idx
            count,mt=cumulative.get((transport_key,idx),(0,Decimal("0")))
            _style(ws,row,c,count,fmt=INT)
            _style(ws,row,c+1,float(mt),fmt=NUM)
        _style(ws,row,total_trips_col,
               f"=SUM({','.join(col(3+2*j)+str(row) for j in range(len(DESTINATION_BUCKETS)))})",
               fmt=INT)
        _style(ws,row,total_mt_col,
               f"=SUM({','.join(col(4+2*j)+str(row) for j in range(len(DESTINATION_BUCKETS)))})",
               fmt=NUM)
    grand=first+len(transporters)
    _style(ws,grand,2,"Grand Total",total=True)
    for c in range(3,total_mt_col+1):
        letter=col(c)
        _style(ws,grand,c,f"=SUM({letter}{first}:{letter}{grand-1})",
               total=True,fmt=INT if c%2 else NUM)
    # Match the supplied peach/orange transporter layout; retain all figures
    # and workbook calculations, with thin visible borders.
    for row in list(range(23,28))+list(range(buyer_row,trip_row+1)):
        for col_idx in range(2,total_mt_col+1):
            cell=ws.cell(row,col_idx)
            if cell.__class__.__name__ == "MergedCell":
                continue
            cell.fill=peach
            cell.border=Border(left=blue_line,right=blue_line,
                               top=blue_line,bottom=blue_line)
            if cell.value is not None:
                cell.font=Font(name="Calibri",size=9,bold=True,color=DARK)
    for row in (28+len(transporters),grand):
        for col_idx in range(2,total_mt_col+1):
            cell=ws.cell(row,col_idx)
            cell.fill=peach
            cell.border=Border(left=blue_line,right=blue_line,
                               top=blue_line,bottom=blue_line)
            cell.font=Font(name="Calibri",size=9,bold=True,color=DARK)
    ws.print_area=f"B1:{col(total_mt_col)}{grand}"


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
    # Trip and material-only exports must not pay to classify every destination.
    matrix,unmapped=(_keymap(active) if report_type in {"destination","transporter"}
                      else ({}, []))
    _,material_unmapped=(_material_counts(active)
                         if report_type in {"material","despatch","transporter"}
                         else ({}, []))
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
