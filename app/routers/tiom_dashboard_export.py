"""Read-only, presentation-ready TIOM dashboard XLSX export.

Calculates the report with the same permission-checked dashboard service used
by the screen. Never trusts browser-submitted KPI numbers.
"""
from __future__ import annotations

from io import BytesIO
import re

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.auth import csrf, get_user
from app.db import get_db
from app.routers.webapp import dashboard_desk

router = APIRouter(prefix="/api/tiom/dashboard", tags=["tiom-dashboard-export"])

NAVY = "102E43"
DARK = "09273B"
TEAL = "008D89"
LIGHT = "E8F5F4"
BLUE = "E8F1F8"
WHITE = "FFFFFF"
TEXT = "19384C"
MUTED = "597386"
BORDER = "D4E3EA"
AMBER = "FFF1D5"
WARNING = "936100"
THIN = Border(*(Side(style="thin", color=BORDER),) * 4)


def clean(value):
    """Preserve actual numeric zeros, missing values and formula-injection safety."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, (dict, list, tuple)):
        return str(value)
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text[:1024]


def val(source, key):
    source = source if isinstance(source, dict) else {}
    return source.get(key)


def fmt(unit="", places=2):
    pattern = "#,##0" + ("." + ("0" * places) if places else "")
    if unit:
        return pattern + ' "' + unit.replace('"', "") + '"'
    return pattern


def metric(label, value, unit="", places=2, note="", alert=False):
    return label, value, unit, places, note, alert


def metric_groups(d):
    k = d.get("kpis") or {}
    p = d.get("production") or {}
    monthly = d.get("monthly") or {}
    bd = d.get("breakdowns") or {}
    allocation_pending = bool(p.get("allocationPending")) or p.get("finalProductionMt") is None
    pending = "Pending allocation"
    final = None if allocation_pending else p.get("finalProductionMt")
    hsd = k.get("hsdLitres")
    ratio = float(hsd) / float(final) if hsd is not None and isinstance(final, (float, int)) and final > 0 else None
    drilling = k.get("drillMeterage")
    dhsd = k.get("drillHsdLitres")
    drill_ratio = float(dhsd) / float(drilling) if dhsd is not None and isinstance(drilling, (int, float)) and drilling > 0 else None
    ob = k.get("obRemovedMt")
    if ob is None:
        ob = k.get("wasteTonnes")
    return [
        ("01  MANAGEMENT SUMMARY", [
            metric("Fresh ROM", p.get("romInputMt"), "t", 2, "Mine-origin production base"),
            metric("Screen direct output", p.get("screenDirectMt"), "t", 2, "Direct screened output"),
            metric("Crusher gross output", p.get("crusherGrossOutputMt"), "t", 2, "Before blend allocation"),
            metric("Final fresh production", pending if allocation_pending else final, "t", 2, "Old stock excluded", allocation_pending),
            metric("OB removed", ob, "t", 2, "Confirmed WB / validated MIS"),
            metric("Old stock / RH", p.get("oldStockExcludedMt"), "t", 2, "Excluded from fresh production", True),
            metric("WB movements", k.get("wbTrips"), "", 0, "Valid weighbridge movements"),
            metric("WB movement tonnes", k.get("wbTonnes"), "t", 2, "Movement audit; not final production"),
        ]),
        ("02  PRODUCTION & RECOVERY", [
            metric("Screen fines", p.get("screenFinesMt"), "t", 2, "Screen fines output"),
            metric("Screen 5–18", p.get("screen518Mt"), "t", 2, "Screen 5–18 output"),
            metric("Plant feed", p.get("plantFeedMt"), "t", 2, "Recorded plant feed"),
            metric("Total crusher feed", p.get("crusherFeedMt"), "t", 2, "Fresh + old stock blend"),
            metric("Fresh crusher output", pending if allocation_pending else p.get("crusherFreshOutputMt"), "t", 2, "Allocated fresh crusher share", allocation_pending),
            metric("Final recovery", pending if allocation_pending else p.get("finalRecoveryPct"), "%", 2, "Fresh final / ROM", allocation_pending),
            metric("Crusher recovery", p.get("crusherRecoveryPct"), "%", 2, "Gross output / feed"),
            metric("Production balance", pending if allocation_pending else p.get("balanceMt"), "t", 2, "ROM less final fresh production", allocation_pending),
        ]),
        ("03  HAULAGE & WB RECONCILIATION", [
            metric("Trips / active hour", k.get("tripsPerHour"), "", 2, "Haulage pace"),
            metric("Average lead", k.get("haulAvgLeadKm"), "km", 3, "Resolved lead"),
            metric("Trip-km / hour", k.get("tripKmPerHour"), "", 2, "Trips × lead / active hour"),
            metric("Tonne-km / hour", k.get("tonKmPerHour"), "", 1, "Tonnes × lead / active hour"),
            metric("Average payload", k.get("avgPayload"), "t", 2, "WB average payload"),
            metric("Average cycle", k.get("avgCycleTime"), "min", 1, "Start to unload"),
            metric("Average loading", k.get("avgLoadingTime"), "min", 1, "Start to loaded"),
            metric("Match rate", k.get("matchRate"), "%", 1, "WB reconciliation"),
            metric("WB ↔ MIS linked", k.get("misWbLinkedTrips"), "", 0, "Linked WB/MIS trips"),
            metric("WB ↔ Field matched", k.get("matched"), "", 0, "Exact matches"),
            metric("WB unmatched", k.get("wbUnmatched"), "", 0, "Requires linking", bool(k.get("wbUnmatched"))),
            metric("Lead missing", k.get("haulLeadMissingTrips"), "", 0, "No guessed distance", bool(k.get("haulLeadMissingTrips"))),
        ]),
        ("04  HSD & EQUIPMENT", [
            metric("HSD issued", hsd, "L", 1, "HSD ledger issues"),
            metric("HSD / trip", k.get("fuelPerTrip"), "L", 2, "Issued-fuel indicator"),
            metric("HSD / final tonne", ratio, "L/t", 3, "Final fresh denominator required", allocation_pending),
            metric("Working equipment", k.get("workingEquipment"), "", 0, "Equipment-shift count"),
            metric("Running loaders", k.get("runningLoaders"), "", 0, "Activity proxy"),
            metric("Running excavators", k.get("runningExcavators"), "", 0, "Activity proxy"),
            metric("Running tippers", k.get("runningTippers"), "", 0, "Activity proxy"),
            metric("Equipment utilization", k.get("equipmentUtilization"), "%", 1, "Recorded activity proxy"),
        ]),
        ("05  DRILLING PERFORMANCE", [
            metric("Drilled holes", k.get("drillHoles"), "", 0, "Recorded hole count"),
            metric("Drill meterage", drilling, "m", 2, "ROM / OB / BHJ / BHQ"),
            metric("Drill metres / hour", k.get("drillMeterPerHour"), "m/h", 2, "Valid HMR"),
            metric("Drill HSD issued", dhsd, "L", 1, "Drill + compressor issues"),
            metric("Drill breakdown", k.get("drillBreakdownHours"), "h", 1, "Recorded downtime"),
            metric("Drill HSD / metre", drill_ratio, "L/m", 3, "Issued litres / recorded metres"),
        ]),
        ("06  MAINTENANCE & MTD", [
            metric("Open breakdowns", bd.get("activeEvents"), "", 0, "Mechanical events"),
            metric("Period downtime", bd.get("periodDowntimeHours"), "h", 1, "Overlapping shift hours"),
            metric("Month fresh output", monthly.get("actual"), "t", 2, "Cumulative through report date"),
            metric("Average daily fresh", monthly.get("avgDaily"), "t", 2, "MTD daily average"),
            metric("Best day output", monthly.get("bestTonnes"), "t", 2, str(monthly.get("bestDay") or "No day")),
            metric("Worst day output", monthly.get("worstTonnes"), "t", 2, str(monthly.get("worstDay") or "No day")),
        ]),
    ]


def report_context(d):
    items = [
        "Date " + str(d.get("fromDate") or "—") + " → " + str(d.get("toDate") or "—"),
        "Shift " + str(d.get("shift") or "ALL"),
    ]
    for key, label in (
        ("materialFilter", "Material"), ("sourceFilter", "Source"),
        ("destinationFilter", "Destination"), ("vehicleFilter", "Vehicle")
    ):
        if d.get(key):
            items.append(label + ": " + str(d[key]))
    return "     •     ".join(items)


def merge_band(ws, row, last_col, text, fill=DARK, color=WHITE, size=13):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    for cols in ws.iter_cols(min_col=1, max_col=last_col, min_row=row, max_row=row):
        for cell in cols:
            cell.fill = PatternFill("solid", fgColor=fill)
    c = ws.cell(row, 1, clean(text))
    c.font = Font(name="Aptos Display", size=size, color=color, bold=True)
    c.alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[row].height = 29 if size <= 13 else 38


def sheet_header(ws, title, context, cols):
    end = max(cols, 7)
    merge_band(ws, 1, end, "NMTPL   |   THAKURANI IRON ORE MINES", size=15)
    merge_band(ws, 2, end, title, fill=TEAL, size=14)
    merge_band(ws, 3, end, context, fill=LIGHT, color=NAVY, size=10)
    ws.freeze_panes = "B6"
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3 if cols > 9 else ws.PAPERSIZE_A4
    ws.print_options.horizontalCentered = True
    ws.sheet_properties.outlinePr.summaryBelow = True
    ws.print_title_rows = "1:5"
    ws.oddFooter.center.text = "NMTPL | TIOM • Operational MIS"
    ws.oddFooter.right.text = "Page &P of &N"


def dashboard_sheet(wb, d):
    ws = wb.active
    ws.title = "KPI Dashboard"
    context = report_context(d)
    sheet_header(ws, "MANAGEMENT DASHBOARD  |  OPERATING KPI SCORECARD", context, 16)
    for col in range(1, 17):
        ws.column_dimensions[get_column_letter(col)].width = 12.6
    ws.row_dimensions[4].height = 11
    row = 5
    count = 0
    for title, group in metric_groups(d):
        merge_band(ws, row, 16, title, fill=NAVY)
        row += 1
        for offset in range(0, len(group), 4):
            cards = group[offset:offset + 4]
            for card_index, (label, value, unit, places, note, warning) in enumerate(cards):
                start = card_index * 4 + 1
                end = start + 3
                for r in (row, row + 1, row + 2):
                    ws.merge_cells(start_row=r, start_column=start, end_row=r, end_column=end)
                    for c in range(start, end + 1):
                        cell = ws.cell(r, c)
                        cell.fill = PatternFill("solid", fgColor=AMBER if warning else (LIGHT if title.startswith("01") else BLUE))
                        cell.border = THIN
                head, val_cell, note_cell = ws.cell(row, start), ws.cell(row+1, start), ws.cell(row+2, start)
                head.value = clean(label)
                head.font = Font(name="Aptos", size=10, bold=True, color=WARNING if warning else MUTED)
                val_cell.value = clean(value) if value is not None else "Not available"
                val_cell.font = Font(name="Aptos Display", size=17, bold=True, color=WARNING if warning else NAVY)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    val_cell.number_format = fmt(unit, places)
                note_cell.value = clean(note)
                note_cell.font = Font(name="Aptos", size=9, color=MUTED)
                for cell in (head, val_cell, note_cell):
                    cell.alignment = Alignment(horizontal="left", vertical="center", indent=1, wrap_text=True)
                count += 1
            ws.row_dimensions[row].height = 23
            ws.row_dimensions[row+1].height = 32
            ws.row_dimensions[row+2].height = 27
            row += 4
        row += 1
    merge_band(ws, row, 16, "REPORTING NOTES & INTERPRETATION", fill=TEAL)
    row += 1
    notes = [
        "Fresh ROM is the production base; old-stock blending and rehandling are NOT additional fresh production.",
        "WB movement tonnes are an audit movement total and must not be added to production or plant output.",
        "Pending allocation / Not available means that the source did not verify that KPI. Do not replace it with zero.",
        "HSD quantities represent issues, not proven consumption. MTD is a separately calculated monthly view.",
    ]
    for note in notes:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=16)
        cell = ws.cell(row, 1, clean("• " + note))
        cell.font = Font(name="Aptos", color=TEXT, size=10)
        cell.alignment = Alignment(wrap_text=True, vertical="center", indent=1)
        ws.row_dimensions[row].height = 27
        row += 1
    ws.print_area = "A1:P" + str(row)
    return count


def detail_sheet(wb, name, title, d, headers, data, widths=None):
    ws = wb.create_sheet(name)
    n = len(headers)
    sheet_header(ws, title, report_context(d), n)
    ws.row_dimensions[4].height = 9
    for i, head in enumerate(headers, 1):
        c = ws.cell(5, i, clean(head))
        c.fill = PatternFill("solid", fgColor=NAVY)
        c.font = Font(name="Aptos", size=10, color=WHITE, bold=True)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = THIN
        ws.column_dimensions[get_column_letter(i)].width = widths[i-1] if widths and i <= len(widths) else 19
    ws.row_dimensions[5].height = 34
    for ri, record in enumerate(data, 6):
        ws.row_dimensions[ri].height = 27
        for ci, raw in enumerate(record, 1):
            c = ws.cell(ri, ci, clean(raw))
            c.font = Font(name="Aptos", size=10, color=TEXT)
            c.fill = PatternFill("solid", fgColor=WHITE if ri % 2 else "F0F7F9")
            c.border = THIN
            c.alignment = Alignment(vertical="center", wrap_text=True, horizontal="right" if isinstance(raw, (int,float)) else "left")
            if isinstance(raw, int) and not isinstance(raw, bool):
                c.number_format = fmt("", 0)
            elif isinstance(raw, float):
                c.number_format = fmt("", 2)
            if str(raw).upper() in {"PENDING", "ALLOCATION PENDING", "EXCLUDED", "UNMAPPED", "MISSING"}:
                c.fill = PatternFill("solid", fgColor=AMBER)
                c.font = Font(name="Aptos", size=10, color=WARNING, bold=True)
    if not data:
        ws.cell(6, 1, "No records returned for selected filters")
        ws.cell(6, 1).font = Font(name="Aptos", italic=True, color=MUTED)
    bottom = max(6, len(data)+5)
    ws.auto_filter.ref = f"A5:{get_column_letter(n)}{bottom}"
    ws.print_area = f"A1:{get_column_letter(n)}{bottom}"
    return ws


def make_workbook(d):
    wb = Workbook()
    count = dashboard_sheet(wb, d)
    def arr(key):
        value = d.get(key)
        return value if isinstance(value, list) else []
    def row(source, keys):
        return [source.get(key) for key in keys]
    prod = arr("productionMaterials")
    detail_sheet(wb, "Production Materials", "MATERIAL & PRODUCTION STAGES", d,
        ["Production material", "Trips", "Period tonnes", "MTD tonnes", "Average payload", "% of ROM", "Treatment"],
        [[x.get("label"),x.get("trips"),x.get("tonnes"),x.get("monthTonnes"),x.get("avgPayload"),x.get("pct"),"EXCLUDED" if x.get("excluded") else x.get("kind") or "Included"] for x in prod],
        [38,13,21,21,19,17,22])
    plants = arr("plantPerformance")
    detail_sheet(wb, "Plant Performance", "SCREEN & CRUSHER • FEED VERSUS OUTPUT", d,
        ["Plant", "Fresh feed t", "Recycle t", "Old stock t", "Gross throughput t", "Fresh / final output t", "Transfer to crusher t", "Variance t", "Recovery %", "Running hours", "TPH"],
        [[x.get("plant"), x.get("freshFeedMt", x.get("feedMt")), x.get("recycleMt"), x.get("blendFeedMt"),
          x.get("grossThroughputMt", x.get("feedMt")), x.get("outputMt") if x.get("outputMt") is not None else "Allocation pending",
          x.get("transferToCrusherMt"), x.get("varianceMt"), x.get("recoveryPct"), x.get("runningHours"), x.get("tph")] for x in plants],
        [25,17,17,17,22,23,23,18,15,18,15])
    detail_sheet(wb, "Shift Comparison", "SHIFT A / B / C PERFORMANCE", d,
        ["Shift", "WB movements", "Movement tonnes", "HSD issued L", "Average payload t"],
        [row(x,["shift","trips","tonnes","fuel","avgPayload"]) for x in arr("shiftComparison")],
        [17,21,23,23,23])
    wb_material = arr("materials")
    sheet = detail_sheet(wb,"WB Material Audit","WEIGHBRIDGE MATERIAL MOVEMENT • NOT FINAL PRODUCTION",d,
        ["Material", "WB trips", "Movement tonnes", "MTD tonnes", "Avg payload", "Share %"],
        [row(x,["label","trips","tonnes","monthTonnes","avgPayload","pct"]) for x in wb_material],
        [38,16,25,23,22,15])
    if wb_material:
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = "Material movement by tonnes • WB audit only"
        chart.y_axis.title = "Material"
        chart.x_axis.title = "Tonnes"
        chart.add_data(Reference(sheet, min_col=3, min_row=5, max_row=5+len(wb_material)), titles_from_data=True)
        chart.set_categories(Reference(sheet, min_col=1, min_row=6, max_row=5+len(wb_material)))
        chart.width = 24
        chart.height = 12
        sheet.add_chart(chart, "H6")
    detail_sheet(wb, "Haulage Routes", "HAULAGE PRODUCTIVITY • ROUTES & LEAD", d,
        ["Source", "Destination", "Mode", "Trips", "Active hours", "Trips/hour", "Average lead km", "Trip-km/hour", "Tonne-km/hour", "Cycle min", "Lead status"],
        [[x.get("source"), x.get("destination"), x.get("routeMode"), x.get("trips"),
          x.get("activeHours"), x.get("tripsPerHour"), x.get("avgLeadKm"), x.get("tripKmPerHour"),
          x.get("tonKmPerHour"), x.get("avgCycleMin"), x.get("leadStatus")] for x in arr("haulagePerformance")],
        [25,28,18,12,18,18,20,20,20,16,19])
    detail_sheet(wb, "Fuel & Equipment", "HSD ISSUES BY EQUIPMENT • NO CONSUMPTION ASSUMED", d,
        ["Machine", "Equipment type", "Issued HSD L", "Matched tonnes", "Litres per tonne"],
        [row(x,["machine","type","litres","tonnes","litresPerTonne"]) for x in arr("fuelByEquipment")],
        [33,24,24,24,23])
    detail_sheet(wb, "Drilling Details", "DRILLING & COMPRESSOR PRODUCTIVITY", d,
        ["Drill set", "Drill hours", "Compressor hours", "Holes", "Meterage", "Metres/hour", "HSD L", "HSD L/metre", "Breakdown hours"],
        [[x.get("label") or x.get("drillSetId"), x.get("drillHours"), x.get("compressorHours"),
          x.get("holes"), x.get("totalMeterage"), x.get("meterPerHour"), x.get("hsdLitres"),
          x.get("litrePerMeter"), x.get("breakdownHours")] for x in (d.get("drilling") or {}).get("rows", [])],
        [31,19,23,15,20,21,20,20,20])
    exceptions = arr("exceptions")
    notes = d.get("notes") if isinstance(d.get("notes"), list) else []
    quality_rows = [[x.get("severity"), x.get("label"), x.get("value"), "Dashboard exception"] for x in exceptions] + [
        ["INFO", note, None, "Source calculation note"] for note in notes
    ]
    prod_summary = d.get("production") or {}
    if prod_summary.get("allocationPending"):
        quality_rows.insert(0, ["REVIEW", "Fresh production allocation pending", None, "Do not infer final fresh output"])
    quality_rows.append(["INFO", "WB movement tonnes are not final production.", None, "Prevent double counting"])
    detail_sheet(wb, "Data Quality", "EXCEPTIONS, GAPS & CALCULATION NOTES", d,
        ["Severity", "Description", "Value", "Interpretation"], quality_rows, [20,85,21,47])
    wb.calculation.fullCalcOnLoad = True
    return wb, count


@router.post("/report.xlsx")
def download_report(request: Request, payload: dict = Body(default={}), db: Session = Depends(get_db)):
    """Authenticated, filter-preserving report produced entirely from server records."""
    csrf(request)
    user = get_user(db, request)
    permitted = {key: payload.get(key) for key in (
        "mode", "fromDate", "toDate", "shift", "materialFilter",
        "sourceFilter", "destinationFilter", "vehicleFilter"
    )}
    dashboard = dashboard_desk(db, user, permitted)
    workbook, count = make_workbook(dashboard)
    if count != 48:
        raise RuntimeError("TIOM KPI report definition has changed unexpectedly")
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    from_date = re.sub("[^0-9-]", "", str(dashboard.get("fromDate") or "date"))
    to_date = re.sub("[^0-9-]", "", str(dashboard.get("toDate") or "date"))
    filename = "TIOM_Management_KPI_Report_" + from_date + "_" + to_date + ".xlsx"
    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="' + filename + '"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
