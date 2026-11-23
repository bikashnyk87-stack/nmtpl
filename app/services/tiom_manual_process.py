"""Process-stage classification for TIOM manual (no-WB) lumps trips.

Material, origin and destination are independent dimensions. A trip can be
both screen output and crusher infeed, but its tonnes must not be counted twice
in a final-production total. This module does not create or change WB weights.
"""
import re

from app.services.tiom_manual_material import canonical_manual_45_material


def _loc_text(location):
    if location is None:
        return ""
    return " ".join(str(getattr(location, field, "") or "")
                    for field in ("location_id", "location_name", "location_type")).upper()


def _is_stock_location(location):
    """Recognise configured stock roles and short numbered stockpiles (S3)."""
    raw=_loc_text(location)
    return (("STOCK" in raw or "STACK" in raw) or
            bool(re.search(r"(?<![A-Z0-9])S[- ]?[0-9]+(?![A-Z0-9])", raw)))


def manual_lump_process_codes(product, source, destination):
    """Return movement facts for an explicitly named manual Lumps material.

    Results describe overlapping process *stages*, not additive tonnage.
    Empty tuple means use ordinary non-lumps classification elsewhere.
    """
    if product is None or canonical_manual_45_material(
        getattr(product, "product_id", ""), getattr(product, "name", "")
    ) != "ROM_LUMPS":
        return ()

    src = _loc_text(source)
    dst = _loc_text(destination)
    from_screen = bool(re.search(r"\b(MSP[ -]?\d*|SCREEN|SCREENING)\b", src))
    from_stock = _is_stock_location(source)
    to_crusher = "CRUSH" in dst or bool(re.search(r"\bOCP\b", dst))
    to_screen = bool(re.search(r"\b(MSP[ -]?\d*|SCREEN|SCREENING)\b", dst))
    to_stock = _is_stock_location(destination)

    if from_stock:
        codes = ["PRODUCT_REHANDLED"]
        if to_crusher:
            codes += ["LUMPS_TO_CRUSHER_FROM_STOCK", "CRUSHER_STOCK_FEED", "CRUSHER_FEED"]
        elif to_screen:
            codes.append("MSP_FEED")
    elif from_screen:
        codes = ["LUMPS_FROM_SCREEN"]
        if to_crusher:
            codes += ["LUMPS_FEED_TO_CRUSHER", "CRUSHER_FEED"]
        elif to_stock:
            codes.append("LUMPS_SHIFTED_TO_STOCK")
        # A screen-to-stock movement remains screen output, not crusher feed;
        # LUMPS_SHIFTED_TO_STOCK is derived only from the report facts.
    else:
        # Mine/face origin: primary excavation, not another screen output.
        codes = ["ROM_LUMPS"]
        if to_crusher:
            codes += ["ROM_FEED_TO_CRUSHER", "CRUSHER_FEED"]
        elif to_screen:
            codes.append("MSP_FEED")
    return tuple(codes)



def manual_rom_process_codes(product, source, destination):
    """General ROM, distinct from named lumps and CLO, including face crusher."""
    if product is None:
        return ()
    product_text = " ".join(str(getattr(product, f, "") or "")
                            for f in ("product_id", "name")).upper()
    normalized = re.sub(r"[^A-Z0-9]+", " ", product_text).strip()
    if not re.search(r"\bROM\b", normalized):
        return ()
    # Named lumps use the more specific classifier, never both.
    if canonical_manual_45_material(
        getattr(product, "product_id", ""), getattr(product, "name", "")
    ) == "ROM_LUMPS":
        return ()
    src = _loc_text(source)
    dst = _loc_text(destination)
    from_stock = _is_stock_location(source)
    to_crusher = "CRUSH" in dst or bool(re.search(r"\bOCP\b", dst))
    to_screen = bool(re.search(r"\b(MSP[ -]?\d*|SCREEN|SCREENING)\b", dst))
    to_stock = _is_stock_location(destination)
    if from_stock:
        codes = ["ROM_REHANDLED"]
        if to_crusher:
            codes += ["ROM_STOCK_TO_CRUSHER", "CRUSHER_STOCK_FEED", "CRUSHER_FEED"]
        elif to_screen:
            codes += ["ROM_STOCK_TO_PLANT_FEED", "MSP_FEED"]
        elif to_stock:
            codes.append("ROM_STOCK_TO_STOCK")
    else:
        codes = ["ROM"]
        if to_crusher:
            codes += ["ROM_FEED_TO_CRUSHER", "CRUSHER_FEED"]
        elif to_screen:
            codes.append("MSP_FEED")
        elif to_stock:
            codes.append("ROM_STOCK_YARD")
    return tuple(codes)


def manual_spillage_process_codes(product, source, destination):
    """Physical re-screen/recycle is not new mine ROM.

    Same-cycle MSP recycle counts for gross throughput only. Material
    withdrawn from a stockpile is an external pass, not new mine production.
    """
    if product is None:
        return ()
    label = re.sub(r"[^A-Z0-9]+", " ", " ".join(
        str(getattr(product, name, "") or "") for name in ("product_id", "name")
    ).upper()).strip()
    if not re.search(r"\bSPILL(?:AGE)?\b", label):
        return ()
    src = _loc_text(source)
    dst = _loc_text(destination)
    from_stock = _is_stock_location(source)
    to_crusher = "CRUSH" in dst or bool(re.search(r"\bOCP\b", dst))
    to_screen = bool(re.search(r"\b(MSP[ -]?\d*|SCREEN|SCREENING)\b", dst))
    if to_crusher:
        return ("SPILLAGE_TO_CRUSHER", "CRUSHER_FEED")
    if to_screen:
        if from_stock:
            return ("SPILLAGE_FROM_STOCK", "PRODUCT_REHANDLED", "MSP_FEED")
        return ("SPILLAGE_RECYCLE_MSP",)
    return ("SPILLAGE_WIP",)


def manual_process_codes(product, source, destination):
    """Dispatch to one exclusive material classifier; facts may span stages."""
    return (manual_lump_process_codes(product, source, destination)
            or manual_rom_process_codes(product, source, destination)
            or manual_spillage_process_codes(product, source, destination))


def unweighed_process_trip_facts(db, first, last, shift="ALL", allowed_shifts=None):
    """Submitted no-WB ROM and lumps. Never re-count a saved WB-linked MIS trip.

    Returns physical movements with explicit MIS trip-factor provenance.
    No inference from similar weights, vehicles or nearby WB timestamps.
    """
    from decimal import Decimal
    from sqlalchemy import select
    from app.models import Location, Product
    from app.site_models import (
        TiomMisReport, TiomMisTripRow, TiomMisTripDetail, TiomMisReconciliation
    )

    stmt = select(TiomMisReport).where(
        TiomMisReport.operating_date >= first,
        TiomMisReport.operating_date <= last,
        TiomMisReport.status == "SUBMITTED",
    )
    if shift != "ALL":
        stmt = stmt.where(TiomMisReport.shift == shift)
    elif allowed_shifts:
        stmt = stmt.where(TiomMisReport.shift.in_(allowed_shifts))
    reports = list(db.scalars(stmt))
    if not reports:
        return []
    report_map = {report.report_id: report for report in reports}
    rows = list(db.scalars(select(TiomMisTripRow).where(
        TiomMisTripRow.report_id.in_(list(report_map))
    )))
    if not rows:
        return []
    row_ids = [row.row_id for row in rows]
    details = {d.row_id: d for d in db.scalars(select(TiomMisTripDetail).where(
        TiomMisTripDetail.row_id.in_(row_ids)
    ))}
    linked = {rec.row_id for rec in db.scalars(select(TiomMisReconciliation).where(
        TiomMisReconciliation.row_id.in_(row_ids),
        TiomMisReconciliation.wb_movement_key.is_not(None),
    ))}
    products = {p.product_id: p for p in db.scalars(select(Product))}
    locations = {location.location_id: location for location in db.scalars(select(Location))}
    result = []
    for row in rows:
        if row.row_id in linked:
            continue
        detail = details.get(row.row_id)
        if detail is None or detail.calculated_qty_mt is None:
            continue
        product = products.get(detail.material_id)
        source = locations.get(detail.source_location_id)
        destination = locations.get(detail.destination_location_id)
        if product is None or source is None or destination is None:
            continue
        codes = manual_process_codes(product, source, destination)
        if not codes:
            continue
        qty = Decimal(detail.calculated_qty_mt)
        if qty <= 0:
            continue
        report = report_map[row.report_id]
        result.append({
            "date": report.operating_date,
            "shift": report.shift,
            "vehicleId": report.vehicle_id,
            "reportId": report.report_id,
            "rowId": row.row_id,
            "source": source,
            "destination": destination,
            "qty": qty,
            "codes": codes,
            "loadingAt": row.loading_at,
            "quantitySource": "MIS_TRIP_FACTOR",
        })
    return result
