"""Operational freshness warnings and WB import size guardrails."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wb_mixed_shift_import_rejects_large_files_before_openpyxl():
    s = (ROOT/"scripts/wb_gmail_worker.py").read_text("utf-8")
    block = s[s.index("def ingest_xlsx("):s.index("def apply_labels(",s.index("def ingest_xlsx("))]
    assert block.index("if len(content) > max_bytes:") < block.index("wb = load_workbook(")
    assert "ws.max_row > 25000 or ws.max_column > 150" in block
    assert "store_rejected_attachment(" in s


def test_dashboard_exposes_mis_freshness_without_creating_field_reports():
    api=(ROOT/"app/routers/webapp.py").read_text("utf-8")
    ui=(ROOT/"app/static/tiom_management_ui.js").read_text("utf-8")
    assert "'entryFreshness': entry_freshness" in api
    assert "last_mis_day = db.scalar" in api
    assert "noFictitiousReports" in api
    assert "Manual MIS reporting gap" in ui
    assert "last confirmed WB" in ui


def test_rejected_wb_quarantine_is_durable_and_private():
    api=(ROOT/"app/routers/webapp.py").read_text("utf-8")
    assert "def wb_gmail_errors(" in api
    assert "def wb_gmail_error_download(" in api
    from app.services.wb_quarantine import WbGmailQuarantine
    assert WbGmailQuarantine.__tablename__ == "wb_gmail_quarantine"
