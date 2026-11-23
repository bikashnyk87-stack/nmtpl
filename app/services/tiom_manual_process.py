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
    from_stock = "STOCK" in src or "STACK" in src
    to_crusher = "CRUSH" in dst or bool(re.search(r"\bOCP\b", dst))
    to_screen = bool(re.search(r"\b(MSP[ -]?\d*|SCREEN|SCREENING)\b", dst))

    if from_stock:
        codes = ["PRODUCT_REHANDLED"]
        if to_crusher:
            codes += ["LUMPS_TO_CRUSHER_FROM_STOCK", "CRUSHER_FEED"]
        elif to_screen:
            codes.append("MSP_FEED")
    elif from_screen:
        codes = ["LUMPS_FROM_SCREEN"]
        if to_crusher:
            codes += ["LUMPS_FEED_TO_CRUSHER", "CRUSHER_FEED"]
        # A screen-to-stock movement remains screen output, not crusher feed;
        # LUMPS_SHIFTED_TO_STOCK is derived only from the report facts.
    else:
        # Mine/face origin: primary excavation, not another screen output.
        codes = ["ROM_LUMPS"]
        if to_crusher:
            codes.append("CRUSHER_FEED")
        elif to_screen:
            codes.append("MSP_FEED")
    return tuple(codes)
