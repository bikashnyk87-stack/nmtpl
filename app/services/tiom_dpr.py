"""TIOM daily/monthly DPR Excel workbook, built from validated saved database facts.

Layout mirrors the attached DPR: Shift A/B/C and combined daily panel; excavation,
plant output, stacking, infeed, drilling, machine HMR, MTD and separate summaries.
Never convert absent measurements or dispatch into a reported zero.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

MIME="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NAVY="15344E"
BLUE="205C79"
TEAL="087C87"
PALE="EAF4F7"
GOLD="FFE9A6"
GREY="EEF1F4"
RED="B91C1C"
WHITE="FFFFFF"
NUM="#,##0.00;[Red](#,##0.00);–"
EXC=[
    ("ROM","ROM"),("ROM_LUMPS","ROM LUMPS"),("SUBGRADE_DUMP","SUBGRADE DUMP"),
    ("SUBGRADE_FEED_PLANT","SUBGRADE FEED PLANT"),("WASTE","WASTE / OB"),
    ("ROM_STOCK_YARD","ROM STOCK YARD"),
    ("ROM_STOCK_TO_PLANT_FEED","ROM STOCK TO PLANT FEED"),
]
OUTPUT=[
    ("SCREEN_FINES","Screened Fines"),("LUMPS_FROM_SCREEN","Screened Lumps"),
    ("SCREEN_5_18","Screened 5-18"),
    ("CRUSHER_FINES","Crusher Fines"),("CRUSHER_5_18","Crusher 5-18"),
    ("TOTAL_PRODUCTION","Final production"),
]
STACK=[
    ("SCREEN_FINES_SHIFTED","Screen Fines shifted"),
    ("CRUSHER_FINES_SHIFTED","Crusher Fines shifted"),
    ("SC_5_18_SHIFTED","5-18 shifted for stacking"),
]
FEED=[
    ("MSP_FEED","MSP / screening plant feed"),
    ("LUMPS_FEED_TO_CRUSHER","Lumps feed to crusher"),
    ("LUMPS_TO_CRUSHER_FROM_STOCK","Lumps from stock to crusher"),
    ("SPILLAGE","Spillage"),
    ("RE_SCREEN_FINES","Re-screen Fines"),
    ("RE_SCREEN_5_18","Re-screen 5-18"),
]
REHANDLE=[
    ("UNSCREENED_5_18","Unscreened 5-18"),
    ("PROJECT_AREA_FINES_TO_STACK","Project Fines to stack"),
    ("SHIFT_5_40_TANKURA","5-40mm (Tankura)"),
]
PLANTS=["MSP-3","MSP-4","MSP-5","MSP-6","Crusher"]
SELECTED=("A","B","C")


def _v(entry,code):
    return (entry or {}).get("metrics",{}).get(code)


def _q(entry,code):
    item=_v(entry,code)
    if not item:
        return None
    return float(item["qty"]) if item.get("qty") is not None else None


def _trips(entry,code):
    item=_v(entry,code)
    return item.get("trips") if item else None


def _fmt(ws):
    ws.sheet_view.showGridLines=False
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.page_setup.fitToWidth=1
    ws.page_setup.fitToHeight=0
    ws.page_setup.orientation="landscape"
    ws.page_setup.paperSize=ws.PAPERSIZE_A3
    ws.page_margins=PageMargins(left=.22,right=.22,top=.36,bottom=.36,header=.14,footer=.14)
    ws.oddFooter.center.text="TIOM | DPR | Source-backed, not a ledger posting"
    ws.oddFooter.right.text="Page &P / &N"


def _heading(ws,r,a,b,label,fill=BLUE):
    ws.merge_cells(start_row=r,start_column=a,end_row=r,end_column=b)
    c=ws.cell(r,a,label)
    c.fill=PatternFill("solid",fgColor=fill)
    c.font=Font(name="Calibri",bold=True,color=WHITE,size=9)
    c.alignment=Alignment(vertical="center",horizontal="left",indent=1)
    ws.row_dimensions[r].height=max(ws.row_dimensions[r].height or 14,19)


def _num(ws,row,col,x):
    c=ws.cell(row,col)
    if x is not None:
        c.value=round(float(x),3)
        c.number_format=NUM
    c.alignment=Alignment(horizontal="right")
    return c


def _table(ws,title,headers,rows,widths):
    _fmt(ws)
    length=len(headers)
    _heading(ws,1,1,length,title,NAVY)
    ws.row_dimensions[1].height=31
    for j,(head,width) in enumerate(zip(headers,widths),start=1):
        c=ws.cell(3,j,head)
        c.font=Font(bold=True,color=WHITE,size=10)
        c.fill=PatternFill("solid",fgColor=BLUE)
        c.alignment=Alignment(wrap_text=True,vertical="center")
        ws.column_dimensions[get_column_letter(j)].width=width
    ws.row_dimensions[3].height=32
    for i,row in enumerate(rows,4):
        for j,val in enumerate(row,1):
            cell=ws.cell(i,j,val)
            if isinstance(val,(int,float,Decimal)):
                cell.number_format=NUM
            if i%2==0:
                cell.fill=PatternFill("solid",fgColor="F3F7FA")
            cell.alignment=Alignment(vertical="top",wrap_text=False)
    ws.freeze_panes="C4"
    ws.auto_filter.ref=f"A3:{get_column_letter(length)}{max(4,len(rows)+3)}"
    ws.print_options.horizontalCentered=True


def _daily_book_page(wb, day, shifts, by_key, cumulative, quality):
    name=day.strftime("%d.%m.%y")
    ws=wb.create_sheet(name)
    _fmt(ws)
    ws.sheet_view.zoomScale=70
    # Each segment is 13 columns, as in the supplied DPR workbook.
    blocks=[1,14,27,40]
    for start in blocks:
        for j in range(start,start+13):
            ws.column_dimensions[get_column_letter(j)].width=10 if j!=start else 17
    for j in range(53,62):
        ws.column_dimensions[get_column_letter(j)].width=16 if j==53 else 13
    _heading(ws,1,1,61,"THAKURANI IRON ORE MINES | DAILY PRODUCTION REPORT | "+day.strftime("%d %b %Y").upper(),NAVY)
    ws.row_dimensions[1].height=30
    for idx,start in enumerate(blocks):
        sh=SELECTED[idx] if idx<3 else "TOTAL"
        _heading(ws,2,start,start+12,
                 day.strftime("%d/%m/%Y")+"   •   "+("SHIFT "+sh if sh!="TOTAL" else "ALL SELECTED SHIFTS"),TEAL if sh!="TOTAL" else NAVY)
        ws.cell(4,start,"EXCAVATION").font=Font(bold=True,color=BLUE)
        for offset,text in [(2,"Trips"),(4,"MT"),(6,"PLANT / PROCESS OUTPUT"),(9,"Trips"),(11,"MT")]:
            ws.cell(4,start+offset,text).font=Font(bold=True,color=BLUE,size=9)
        entry=by_key.get((day,sh)) if sh!="TOTAL" else None
        for ri,(code,label) in enumerate(EXC,5):
            ws.cell(ri,start,label)
            if sh=="TOTAL":
                for offset in (2,4):
                    col=get_column_letter(start+offset)
                    src=[f"{get_column_letter(blocks[n]+offset)}{ri}" for n in range(3) if SELECTED[n] in shifts]
                    if src:ws.cell(ri,start+offset,"=SUM("+",".join(src)+")").number_format=NUM
            elif entry:
                _num(ws,ri,start+2,_trips(entry,code))
                _num(ws,ri,start+4,_q(entry,code))
        for ri,(code,label) in enumerate(OUTPUT,5):
            ws.cell(ri,start+6,label)
            if sh=="TOTAL":
                for offset in (9,11):
                    src=[f"{get_column_letter(blocks[n]+offset)}{ri}" for n in range(3) if SELECTED[n] in shifts]
                    if src:ws.cell(ri,start+offset,"=SUM("+",".join(src)+")").number_format=NUM
            elif entry:
                _num(ws,ri,start+9,_trips(entry,code))
                _num(ws,ri,start+11,_q(entry,code))
        ws.cell(12,start,"TOTAL EXCAVATION")
        ws.cell(12,start+6,"FINAL PRODUCTION")
        if sh=="TOTAL":
            for offset,colref in ((4,"E"),(11,"L")):
                # Use complete output totals rather than summing intermediate output.
                src=[f"{get_column_letter(blocks[n]+offset)}12" for n in range(3) if SELECTED[n] in shifts]
                if src:ws.cell(12,start+offset,"=SUM("+",".join(src)+")").number_format=NUM
        elif entry:
            _num(ws,12,start+4,_q(entry,"TOTAL_EXCAVATION"))
            _num(ws,12,start+11,_q(entry,"TOTAL_PRODUCTION"))
        for j in range(start,start+13):
            c=ws.cell(12,j);c.fill=PatternFill("solid",fgColor=GOLD);c.font=Font(bold=True,color=NAVY,size=9)
        _heading(ws,13,start,start+12,"STACKING / FINISHED MATERIAL",BLUE)
        for ri,(code,label) in enumerate(STACK,14):
            ws.cell(ri,start,label)
            if sh=="TOTAL":
                src=[f"{get_column_letter(blocks[n]+4)}{ri}" for n in range(3) if SELECTED[n] in shifts]
                if src:ws.cell(ri,start+4,"=SUM("+",".join(src)+")").number_format=NUM
            elif entry:
                _num(ws,ri,start+2,_trips(entry,code))
                _num(ws,ri,start+4,_q(entry,code))
        _heading(ws,18,start,start+12,"PIT / QUARRY EXCAVATION • SOURCE MAPPING",BLUE)
        ws.cell(19,start,"Quarry / bench")
        ws.cell(19,start+5,"Load / trip evidence")
        ws.cell(20,start,"Area-wise split")
        ws.cell(20,start+5,"See Source Data; quarry master mapping required")
        _heading(ws,22,start,start+12,"PLANT INFEED / REHANDLING",BLUE)
        for ri,(code,label) in enumerate(FEED,23):
            ws.cell(ri,start,label)
            if sh=="TOTAL":
                src=[f"{get_column_letter(blocks[n]+4)}{ri}" for n in range(3) if SELECTED[n] in shifts]
                if src:ws.cell(ri,start+4,"=SUM("+",".join(src)+")").number_format=NUM
            elif entry:
                _num(ws,ri,start+2,_trips(entry,code))
                _num(ws,ri,start+4,_q(entry,code))
        _heading(ws,30,start,start+12,"DRILLING REPORT",BLUE)
        for off,name0 in [(0,"Drill set"),(6,"Hours"),(8,"Holes"),(10,"Meterage")]:
            ws.cell(31,start+off,name0).font=Font(bold=True,color=BLUE,size=9)
        drill=(entry or {}).get("drilling",[]) if sh!="TOTAL" else []
        for k,d in enumerate(drill[:8],32):
            ws.cell(k,start,str(d.get("label",""))[:24])
            _num(ws,k,start+6,d.get("drillHours"))
            _num(ws,k,start+8,d.get("holes"))
            _num(ws,k,start+10,d.get("meterage"))
        if sh=="TOTAL":
            for k in range(32,40):
                for off in [6,8,10]:
                    src=[f"{get_column_letter(blocks[n]+off)}{k}" for n in range(3) if SELECTED[n] in shifts]
                    if src:ws.cell(k,start+off,"=SUM("+",".join(src)+")").number_format=NUM
        _heading(ws,41,start,start+12,"MACHINERY & PLANT RUNNING HOURS",BLUE)
        ws.cell(42,start,"Plant / machine")
        ws.cell(42,start+6,"HMR (hours)")
        ws.cell(42,start+9,"TPH")
        for k,p in enumerate(PLANTS,43):
            ws.cell(k,start,p)
            if sh=="TOTAL":
                src=[f"{get_column_letter(blocks[n]+6)}{k}" for n in range(3) if SELECTED[n] in shifts]
                if src:ws.cell(k,start+6,"=SUM("+",".join(src)+")").number_format=NUM
            elif entry:
                hours=(entry.get("plantHours") or {}).get(p)
                _num(ws,k,start+6,hours)
                prod=(entry.get("plantProduction") or {}).get(p)
                _num(ws,k,start+9,(prod/hours) if hours is not None and hours>0 and prod is not None else None)
        _heading(ws,50,start,start+12,"SHIFT REMARKS / REPORT CONTROLS",BLUE)
        if sh=="TOTAL":
            ws.cell(51,start,"Source: confirmed WB + submitted MIS + exceptions")
            ws.cell(52,start,"All totals are movement-category totals, not additive mine production")
        elif entry:
            ws.cell(51,start,"WB valid movements")
            _num(ws,51,start+4,entry.get("wbValid"))
            ws.cell(52,start,"WB REVIEW")
            _num(ws,52,start+4,entry.get("wbReview"))
            ws.cell(53,start,"Shift Production")
            ws.cell(53,start+5,str(entry.get("productionStatus") or "No shift form"))
            notes=entry.get("warnings") or []
            for k,note in enumerate(notes[:5],54):
                ws.cell(k,start,str(note)[:150])
        else:
            ws.cell(51,start,"SHIFT NOT SELECTED")
    _heading(ws,2,53,61,"MTD SNAPSHOT / DATA QUALITY",NAVY)
    ws.cell(4,53,"Material / output")
    ws.cell(4,56,"Selected date MT")
    ws.cell(4,59,"MTD MT")
    summary_codes=[("ROM","Fresh ROM"),("WASTE","Waste / OB"),("SUBGRADE_DUMP","Sub-grade dump"),
        ("SCREEN_FINES","Screen Fines"),("CRUSHER_FINES","Crusher Fines"),("TOTAL_PRODUCTION","Final output"),
        ("TOTAL_EXCAVATION","Excavation total"),("SCREEN_FINES_SHIFTED","Stacked Screen Fines"),
        ("CRUSHER_FINES_SHIFTED","Stacked Crusher Fines")]
    for ri,(code,label) in enumerate(summary_codes,5):
        ws.cell(ri,53,label)
        _num(ws,ri,56,sum(_q(by_key.get((day,s)),code) or 0 for s in shifts))
        _num(ws,ri,59,cumulative.get((day,code)))
    ws.cell(16,53,"Report basis")
    ws.cell(17,53,"WB confirmed + submitted MIS + manual exceptions")
    ws.cell(19,53,"Dispatch / Stock balance")
    ws.cell(20,53,"PENDING: no authenticated dispatch / stock ledger")
    ws.cell(22,53,"Quality warnings")
    for ri,note in enumerate(quality.get(day,[])[:7],23):
        ws.cell(ri,53,str(note)[:125])
    ws.print_area="A1:BI60"
    ws.freeze_panes="A4"
    ws.sheet_properties.tabColor=TEAL


def build_dpr_workbook(payload):
    """Return in-memory xlsx, with one wide DPR sheet per day plus audits."""
    wb=Workbook()
    wb.remove(wb.active)
    entries=payload["entries"]
    by_key={(date.fromisoformat(r["date"]),r["shift"]):r for r in entries}
    dates=[date.fromisoformat(x) for x in payload["dates"]]
    shifts=tuple(payload["shifts"])
    # MTD is recalculated from the first of each month, not from prior-sheet formulas.
    running=defaultdict(float)
    cumulative={}
    for d in sorted({date.fromisoformat(x["date"]) for x in payload.get("mtdEntries",[])}):
        if d.day==1:
            running=defaultdict(float)
        for code in sorted({k for r in payload.get("mtdEntries",[]) if r["date"]==str(d) for k in r["metrics"]}):
            running[code]+=sum(_q(r,code) or 0 for r in payload["mtdEntries"] if r["date"]==str(d))
        for code,val in running.items():
            cumulative[(d,code)]=round(val,3)
    quality=defaultdict(list)
    for entry in entries:
        d=date.fromisoformat(entry["date"])
        for msg in entry.get("quality",[]):
            if msg not in quality[d]:
                quality[d].append(msg)

    summary=[]
    for d in dates:
        for sh in shifts:
            e=by_key.get((d,sh))
            if not e:continue
            summary.append([str(d),sh,e.get("productionStatus"),e.get("wbValid"),
                e.get("wbReview"),_trips(e,"ROM"),_q(e,"ROM"),_q(e,"WASTE"),
                _q(e,"SUBGRADE_DUMP"),_q(e,"SCREEN_FINES"),_q(e,"SCREEN_5_18"),
                _q(e,"CRUSHER_FINES"),_q(e,"CRUSHER_5_18"),_q(e,"TOTAL_PRODUCTION"),
                _q(e,"TOTAL_EXCAVATION"),e.get("drillHoles"),e.get("drillMetres"),
                e.get("drillHours"),len(e.get("quality",[]))])
    _table(wb.create_sheet("Summary"),"TIOM | DAILY PRODUCTION SUMMARY",
        ["Date","Shift","Shift Form","Valid WB","WB Review","ROM Trips","ROM MT","OB MT",
         "Sub-grade MT","Screen Fines MT","Screen 5-18 MT","Crusher Fines MT",
         "Crusher 5-18 MT","Final production MT","Excavation MT",
         "Drill Holes","Drill Metres","Drill HMR","Warnings"],summary,
        [14,9,17,11,11,12,13,13,16,19,17,20,20,22,18,14,18,15,12])
    for d in dates:
        _daily_book_page(wb,d,shifts,by_key,cumulative,quality)
    stack_summary=[]
    stacking=[]
    drilling=[]
    raw=[]
    warning_rows=[]
    for e in entries:
        dateval=e["date"];sh=e["shift"]
        stack_summary.append([dateval,sh]+[_q(e,code) for code,_ in STACK]+[
            _q(e,"TOTAL_PRODUCTION"),None,None,"No dispatch / closing stock ledger connected"])
        for code,label in STACK+REHANDLE:
            stacking.append([dateval,sh,code,label,_trips(e,code),_q(e,code),(_v(e,code) or {}).get("source")])
        for code,data in sorted(e["metrics"].items()):
            raw.append([dateval,sh,code,data.get("qty"),data.get("trips"),data.get("source"),e.get("productionStatus")])
        for row in e.get("drilling",[]):
            drilling.append([dateval,sh,row.get("label"),row.get("holes"),row.get("meterage"),
                row.get("drillHours"),row.get("metersPerHour"),row.get("remarks")])
        for msg in e.get("quality",[]):
            warning_rows.append([dateval,sh,"REVIEW",msg])
    _table(wb.create_sheet("Stack Summary"),"TIOM | STACK SUMMARY • DISPATCH NOT YET CONNECTED",
           ["Date","Shift"]+[v for _,v in STACK]+["Processed MT","Dispatch MT","Closing Stock MT","Data source note"],
           stack_summary,[14,10,23,24,24,18,17,21,53])
    _table(wb.create_sheet("Stacking"),"TIOM | SHIFT-WISE STACKING / REHANDLING",
           ["Date","Shift","Code","Movement","Trips","MT","Source"],
           stacking,[14,11,35,35,13,18,26])
    _table(wb.create_sheet("Drilling Detail"),"TIOM | SAVED DRILLING WORK / HOURS",
           ["Date","Shift","Drill Set","Holes","Meterage m","Drill HMR hrs","Metres / Hr","Remarks"],
           drilling,[14,11,30,14,17,18,17,65])
    _table(wb.create_sheet("Source Data"),"TIOM | TRACEABLE CATEGORY TOTALS BY DATE / SHIFT",
           ["Date","Shift","Movement Code","Quantity MT","Trips (when verified)","Authoritative Source","Shift Report Status"],
           raw,[14,10,41,20,24,29,23])
    warning_rows.append(["—","ALL","PENDING","Dispatch, despatch destinations and closing stock require a trusted ledger; values intentionally blank."])
    warning_rows.append(["—","ALL","METHOD","WB weights are measured; manual factor quantities are estimated. Screen/Crusher output not added to excavation."])
    _table(wb.create_sheet("Data Quality"),"TIOM | DPR GENERATION / MISSING SOURCE CONTROL",
           ["Date","Shift","Level","Finding / missing mapping"],warning_rows,[17,12,15,120])
    summary_sheet=wb["Summary"]
    summary_sheet.sheet_properties.tabColor=NAVY
    wb.active=0
    buf=BytesIO()
    wb.save(buf);buf.seek(0)
    return buf
