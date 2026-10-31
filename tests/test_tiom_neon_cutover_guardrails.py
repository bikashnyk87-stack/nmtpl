"""Regression guardrails after Render-to-Neon cutover (2026-10-31).

These tests protect existing business data and user-visible dashboard reads.
They do not require a live Neon connection or mutate any database.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hsd_cannot_be_zeroed_by_environment_flag_on_restart():
    src = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "TIOM_HSD_RESET_BLOCKED" in src
    assert "def _zero_tiom_hsd_test_data(" not in src
    assert "UPDATE hsd_issue_allocation SET litres=0" not in src
    assert "UPDATE hsd_purchase_lot SET litres_received=0" not in src


def test_dashboard_read_does_not_write_missing_wb_mapping():
    src = (ROOT / "app/routers/webapp.py").read_text(encoding="utf-8")
    start = src.index("def dashboard_desk(")
    end = src.index("def ", start + 5)
    dashboard = src[start:end]
    assert "missing_canonical" in dashboard
    assert "wb_canonical_all.update(canonicalize_wb_rows" not in dashboard
    assert "import/reconciliation required" in dashboard


def test_wb_ingestion_still_writes_canonical_mapping():
    src = (ROOT / "app/routers/webapp.py").read_text(encoding="utf-8")
    assert "canonicalize_wb_rows(db,new_wb_rows)" in src
    src = (ROOT / "app/services/tiom_location_erp.py").read_text(encoding="utf-8")
    assert "_lock_wb_canonicalization(db)" in src
    assert "pg_advisory_xact_lock" in src
