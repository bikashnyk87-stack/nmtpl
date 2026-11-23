"""Evidence-aware TIOM mass balance: no estimates masquerading as measurements."""
from decimal import Decimal
from app.services.tiom_mass_balance import calculate_tiom_mass_balance


def facts(**items):
    return {key: {"WB": Decimal(str(value))} for key, value in items.items()}


def test_22_nov_screen_observed_gap_does_not_become_verified_stock_or_lumps():
    result = calculate_tiom_mass_balance({
        "MSP_FEED": {"WB": Decimal("933.64")},
        "SCREEN_FINES": {"WB": Decimal("299.32")},
        "LUMPS_FROM_SCREEN": {"MIS_FACTOR": Decimal("990")},
        "LUMPS_FEED_TO_CRUSHER": {"MIS_FACTOR": Decimal("990")},
        "CRUSHER_FEED": {"MIS_FACTOR": Decimal("990")},
        "CRUSHER_FINES": {"WB": Decimal("356.70")},
    })
    assert result["msp"]["candidateLumpsMt"] == 634.32
    assert result["msp"]["recordedLumpsMt"] == 990
    assert result["msp"]["observedDifferenceMt"] == -355.68
    assert result["msp"]["verifiedVarianceMt"] is None
    assert result["msp"]["status"] == "PENDING_SOURCE_INPUT"
    assert result["crusher"]["totalFeedMt"] == 990
    assert result["crusher"]["verifiedVarianceMt"] is None
    assert result["stock"]["verifiedVarianceMt"] is None
    lumps = next(x for x in result["routes"] if x["code"] == "LUMPS_FROM_SCREEN")
    assert lumps["measuredMt"] == 0
    assert lumps["estimatedMt"] == 990


def test_internal_rescreen_changes_throughput_not_external_feed():
    baseline = calculate_tiom_mass_balance(facts(
        MSP_FEED=1000, SCREEN_FINES=300, SCREEN_5_18=100, LUMPS_FROM_SCREEN=600
    ))
    recycled = calculate_tiom_mass_balance(facts(
        MSP_FEED=1000, SPILLAGE_RECYCLE_MSP=100,
        SCREEN_FINES=300, SCREEN_5_18=100, LUMPS_FROM_SCREEN=600
    ))
    assert baseline["msp"]["externalFeedMt"] == recycled["msp"]["externalFeedMt"] == 1000
    assert baseline["msp"]["grossPassThroughMt"] == 1000
    assert recycled["msp"]["grossPassThroughMt"] == 1100
    assert recycled["msp"]["observedDifferenceMt"] == 0


def test_multi_stage_crusher_sources_are_not_added_twice():
    result = calculate_tiom_mass_balance(facts(
        CRUSHER_FEED=200,
        ROM_FEED_TO_CRUSHER=80,
        LUMPS_FEED_TO_CRUSHER=70,
        ROM_STOCK_TO_CRUSHER=50,
        CRUSHER_STOCK_FEED=50,
        CRUSHER_FINES=180
    ))
    assert result["crusher"]["totalFeedMt"] == 200
    assert result["crusher"]["sourceBreakdown"]["fromRomStockMt"] == 50
    assert result["crusher"]["sourceUnclassifiedMt"] == 0
    assert result["crusher"]["observedDifferenceMt"] == 20
    assert result["crusher"]["verifiedVarianceMt"] is None


def test_complete_evidence_allows_variance_but_does_not_approve_it():
    inventory = {
        "mspOpeningWipMt": 20, "mspClosingWipMt": 10,
        "mspRejectMt": 5, "mspLossMt": 5,
        "crusherOpeningWipMt": 0, "crusherClosingWipMt": 5,
        "crusherRejectMt": 5, "crusherLossMt": 0,
        "stockOpeningMt": 20, "stockClosingMt": 30,
        "stockOtherReceiptsMt": 0, "stockOtherIssuesMt": 0,
    }
    result = calculate_tiom_mass_balance(facts(
        MSP_FEED=1000, SCREEN_FINES=200, SCREEN_5_18=100,
        LUMPS_FROM_SCREEN=700, CRUSHER_FEED=100, CRUSHER_FINES=90,
        ROM_STOCK_YARD=20, ROM_STOCK_TO_CRUSHER=10
    ), inventory)
    assert result["msp"]["verifiedVarianceMt"] == 0
    assert result["crusher"]["verifiedVarianceMt"] == 0
    assert result["stock"]["verifiedVarianceMt"] == 0
    assert result["status"] == "AVAILABLE_FOR_RECONCILIATION"


def test_stock_receipts_are_only_explicit_destination_movements():
    data = calculate_tiom_mass_balance(facts(
        LUMPS_FROM_SCREEN=990, LUMPS_FEED_TO_CRUSHER=900,
        LUMPS_SHIFTED_TO_STOCK=45, ROM_STOCK_YARD=20,
        LUMPS_TO_CRUSHER_FROM_STOCK=45, ROM_STOCK_TO_PLANT_FEED=10
    ))
    assert data["stock"]["observedReceiptsMt"] == 65
    assert data["stock"]["observedIssuesMt"] == 55
    assert data["stock"]["verifiedVarianceMt"] is None


def test_absent_records_not_written_as_zero():
    data = calculate_tiom_mass_balance({})
    assert data["msp"]["externalFeedMt"] is None
    assert data["crusher"]["totalFeedMt"] is None
    assert data["msp"]["candidateLumpsMt"] is None
    assert data["msp"]["verifiedVarianceMt"] is None
    assert data["stock"]["status"] == "PENDING_STOCK_LEDGER"


def test_mixed_sources_keep_measurement_provenance():
    data = calculate_tiom_mass_balance({
        "CRUSHER_FEED": {"WB": Decimal("100"), "MIS_FACTOR": Decimal("90")}
    })
    row = next(x for x in data["routes"] if x["code"] == "CRUSHER_FEED")
    assert row["qtyMt"] == 190
    assert row["measuredMt"] == 100
    assert row["estimatedMt"] == 90
    assert data["measurement"]["estimatedRouteCount"] >= 1
