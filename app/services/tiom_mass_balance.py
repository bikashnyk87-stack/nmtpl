"""Read-only TIOM material-flow and mass-balance model.

All figures are tonnes and represent a common selected operating period.
WB movements are measured; MIS factor rows are estimates. A material's
appearance at more than one stage is expected, so *route facts are not additive*.

TIOM has no WIP measurement system. WIP is not a required input, and any
input/output difference is an *unexplained provisional variance*, never
automatically assigned to WIP, rejects, loss or stock. Stock closing balance
also remains unknown without an actual stock source.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

ROUTES = (
    ("ROM", "Fresh mine ROM"),
    ("MSP_FEED", "ROM / stock feed entering MSP"),
    ("ROM_FEED_TO_CRUSHER", "Mine-face ROM / lumps to crusher"),
    ("ROM_STOCK_TO_CRUSHER", "ROM stock to crusher"),
    ("SCREEN_FINES", "MSP screen fines"),
    ("SCREEN_5_18", "MSP CLO 5–18"),
    ("RE_SCREEN_FINES", "Recovered/re-screened fines"),
    ("RE_SCREEN_5_18", "Recovered/re-screened CLO"),
    ("LUMPS_FROM_SCREEN", "Lumps produced by MSP"),
    ("LUMPS_FEED_TO_CRUSHER", "MSP lumps to crusher"),
    ("LUMPS_SHIFTED_TO_STOCK", "MSP lumps to stock"),
    ("LUMPS_TO_CRUSHER_FROM_STOCK", "Lumps stock to crusher"),
    ("SPILLAGE_RECYCLE_MSP", "Internal MSP re-screen / recycle"),
    ("SPILLAGE_FROM_STOCK", "Stock spillage reintroduced to MSP"),
    ("SPILLAGE_TO_CRUSHER", "Spillage to crusher"),
    ("SPILLAGE_WIP", "Spillage awaiting routing (recorded)"),
    ("CRUSHER_BLEND_FEED", "Company old-stock crusher blend"),
    ("CRUSHER_STOCK_FEED", "Crusher feed withdrawn from stock"),
    ("CRUSHER_FEED", "Total physical crusher feed"),
    ("CRUSHER_FINES", "Crusher fines output"),
    ("CRUSHER_5_18", "Crusher CLO output"),
    ("ROM_STOCK_YARD", "ROM received by stock"),
    ("ROM_STOCK_TO_PLANT_FEED", "ROM stock issued to MSP"),
)


def _decimal(value):
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return amount if amount.is_finite() else None


def _n(value):
    return round(float(value), 2) if value is not None else None


def calculate_tiom_mass_balance(facts_by_source, inventory=None):
    """Reconcile observed movements without requiring unmeasured WIP.

    `facts_by_source` is {code: {WB: mt, MIS: mt, MANUAL: mt}}.
    Stage facts overlap across processes. The unallocated difference is
    informational only and never creates an inventory, scrap or loss entry.
    Optional *stock* evidence is accepted if independently established.
    """
    source = facts_by_source or {}
    inv = inventory or {}

    def src(code):
        raw = source.get(code) or {}
        if not isinstance(raw, dict):
            return {}
        out = {}
        for key, value in raw.items():
            qty = _decimal(value)
            if qty is not None:
                out[str(key).upper()] = qty
        return out

    def amount(code):
        return sum(src(code).values(), Decimal("0"))

    def recorded(code):
        return bool(src(code))

    def add(*codes):
        return sum((amount(code) for code in codes), Decimal("0"))

    routes = []
    for code, label in ROUTES:
        values = src(code)
        routes.append({
            "code": code, "label": label,
            "recorded": bool(values),
            "qtyMt": _n(sum(values.values(), Decimal("0"))) if values else None,
            "measuredMt": _n(values["WB"]) if "WB" in values else None,
            "estimatedMt": (_n(sum((value for key, value in values.items()
                                    if key != "WB"), Decimal("0")))
                             if any(key != "WB" for key in values) else None),
            "sources": {key: _n(value) for key, value in values.items()},
        })

    msp_feed = amount("MSP_FEED")
    msp_recycle = amount("SPILLAGE_RECYCLE_MSP")
    msp_final = add("SCREEN_FINES", "SCREEN_5_18",
                    "RE_SCREEN_FINES", "RE_SCREEN_5_18")
    screened_lumps = amount("LUMPS_FROM_SCREEN")
    crusher_feed = amount("CRUSHER_FEED")
    crusher_output = add("CRUSHER_FINES", "CRUSHER_5_18")
    # Source-of-feed entries can overlap CRUSHER_FEED: expose them as a
    # provenance breakdown, never add them on top of CRUSHER_FEED.
    crusher_sources = {
        "fromMspLumpsMt": _n(amount("LUMPS_FEED_TO_CRUSHER")),
        "fromFaceRomMt": _n(amount("ROM_FEED_TO_CRUSHER")),
        "fromRomStockMt": _n(amount("ROM_STOCK_TO_CRUSHER")),
        "fromLumpsStockMt": _n(amount("LUMPS_TO_CRUSHER_FROM_STOCK")),
        "fromSpillageMt": _n(amount("SPILLAGE_TO_CRUSHER")),
        "companyBlendMt": _n(amount("CRUSHER_BLEND_FEED")),
    }
    known_crusher_sources = (
        amount("LUMPS_FEED_TO_CRUSHER") + amount("ROM_FEED_TO_CRUSHER")
        + amount("ROM_STOCK_TO_CRUSHER") + amount("LUMPS_TO_CRUSHER_FROM_STOCK")
        + amount("SPILLAGE_TO_CRUSHER") + amount("CRUSHER_BLEND_FEED")
    )
    has_msp_feed = recorded("MSP_FEED")
    has_msp_output = any(recorded(code) for code in (
        "SCREEN_FINES", "SCREEN_5_18", "RE_SCREEN_FINES",
        "RE_SCREEN_5_18", "LUMPS_FROM_SCREEN"
    ))
    has_crusher_feed = recorded("CRUSHER_FEED")
    has_crusher_output = recorded("CRUSHER_FINES") or recorded("CRUSHER_5_18")

    # Only a residual from known movement data. No WIP, loss or stock
    # quantity is assumed, and this is not approved lumps production.
    provisional_lumps = msp_feed - msp_final if has_msp_feed and has_msp_output else None
    observed_msp_difference = (
        msp_feed - (msp_final + screened_lumps)
        if has_msp_feed and has_msp_output else None
    )
    observed_crusher_difference = (
        crusher_feed - crusher_output if has_crusher_feed and has_crusher_output else None
    )
    stock_open = _decimal(inv.get("stockOpeningMt"))
    stock_close = _decimal(inv.get("stockClosingMt"))
    stock_other_in = _decimal(inv.get("stockOtherReceiptsMt"))
    stock_other_out = _decimal(inv.get("stockOtherIssuesMt"))
    stock_complete = all(x is not None for x in (
        stock_open, stock_close, stock_other_in, stock_other_out
    ))
    stock_receipts = add("ROM_STOCK_YARD", "LUMPS_SHIFTED_TO_STOCK")
    stock_issues = add("ROM_STOCK_TO_PLANT_FEED", "ROM_STOCK_TO_CRUSHER",
                       "LUMPS_TO_CRUSHER_FROM_STOCK", "SPILLAGE_FROM_STOCK")
    stock_variance = (
        stock_open + stock_receipts + stock_other_in
        - stock_issues - stock_other_out - stock_close
        if stock_complete else None
    )

    # Site has no WIP capture. Only missing movement sources can block the
    # indicative comparison. Rejects, inter-shift hold-up, sampling/moisture
    # and scale/factor differences remain possible explanations, not inputs.
    missing_msp = ([] if has_msp_feed else ["MSP feed movements"]) + (
        [] if has_msp_output else ["MSP output movements"])
    missing_crusher = ([] if has_crusher_feed else ["Crusher feed movements"]) + (
        [] if has_crusher_output else ["Crusher output movements"])
    missing_stock = [label for key, label in (
        ("stockOpeningMt", "Opening stock"),
        ("stockClosingMt", "Closing stock"),
        ("stockOtherReceiptsMt", "Other stock receipts"),
        ("stockOtherIssuesMt", "Other stock issues"),
    ) if _decimal(inv.get(key)) is None]

    return {
        "status": ("PROVISIONAL_RECONCILIATION"
                   if observed_msp_difference is not None
                   or observed_crusher_difference is not None
                   else "INSUFFICIENT_MOVEMENT_DATA"),
        "unit": "MT",
        "method": "OBSERVED_INPUT_OUTPUT_NO_WIP",
        "wipCapture": "NOT_AVAILABLE_NOT_REQUIRED",
        "routes": routes,
        "msp": {
            "status": "PROVISIONAL" if observed_msp_difference is not None else "AWAITING_MOVEMENTS",
            "externalFeedMt": _n(msp_feed) if has_msp_feed else None,
            "internalRecycleMt": _n(msp_recycle) if recorded("SPILLAGE_RECYCLE_MSP") else None,
            "grossPassThroughMt": _n(msp_feed + msp_recycle) if has_msp_feed else None,
            "screenFinesMt": _n(amount("SCREEN_FINES")) if recorded("SCREEN_FINES") else None,
            "screenCloMt": _n(amount("SCREEN_5_18")) if recorded("SCREEN_5_18") else None,
            "reScreenOutputsMt": _n(add("RE_SCREEN_FINES", "RE_SCREEN_5_18")),
            "recordedLumpsMt": _n(screened_lumps) if recorded("LUMPS_FROM_SCREEN") else None,
            "candidateLumpsMt": _n(provisional_lumps),
            "observedDifferenceMt": _n(observed_msp_difference),
            "verifiedVarianceMt": None,
            "missing": missing_msp,
            "note": "This is an unexplained input-output difference, not WIP, rejects or loss. No WIP entry is required; recycle is internal, not additional feed.",
        },
        "crusher": {
            "status": "PROVISIONAL" if observed_crusher_difference is not None else "AWAITING_MOVEMENTS",
            "totalFeedMt": _n(crusher_feed) if has_crusher_feed else None,
            "recordedOutputMt": _n(crusher_output) if has_crusher_output else None,
            "sourceBreakdown": crusher_sources,
            "sourceUnclassifiedMt": _n(crusher_feed - known_crusher_sources)
                if has_crusher_feed else None,
            "observedDifferenceMt": _n(observed_crusher_difference),
            "verifiedVarianceMt": None,
            "missing": missing_crusher,
            "note": "The observed difference is unexplained, not automatically WIP or loss. Origin breakdown may remain incomplete; stock-origin feed is not fresh production.",
        },
        "stock": {
            "status": "PENDING_STOCK_LEDGER" if stock_variance is None else "CALCULATED",
            "observedReceiptsMt": _n(stock_receipts),
            "observedIssuesMt": _n(stock_issues),
            "verifiedVarianceMt": _n(stock_variance),
            "missing": missing_stock,
            "note": "Known movement categories only; a verified closing balance requires all stock locations, other receipts/issues and physical stock measurements.",
        },
        "measurement": {
            "estimatedRouteCount": sum(bool(row["recorded"] and row["estimatedMt"])
                                       for row in routes),
            "note": "WB quantities are weighed; MIS trip-factor/manual entries are estimates and must not be silently equated.",
        },
    }
