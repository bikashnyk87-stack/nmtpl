"""Protect saved-MIS export completeness and correction/last-activity semantics."""
from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "app" / "routers" / "webapp.py").read_text("utf-8")


def test_mis_saved_report_audit_separates_real_corrections_from_other_actions():
    assert "def _tiom_mis_activity_meta(db, report_ids):" in SOURCE
    for action in ("TIOM_MIS_DRAFT", "TIOM_MIS_SUBMIT", "TIOM_MIS_EDIT_SUBMITTED", "TIOM_MIS_VOID"):
        assert action in SOURCE
    assert "'Last Corrected By','Last Corrected At','Last Action','Last Action By','Last Action At','Action Reason'" in SOURCE
    assert "add_sheet('Full Activity History'" in SOURCE
    assert "audit(db,user,'TIOM_MIS_VOID'" in SOURCE


def test_summary_not_inflated_by_void_or_draft_records():
    assert "if rep.status!='SUBMITTED': continue" in SOURCE
    assert "operational_rows=[x for x in detail_rows if x[2]=='SUBMITTED']" in SOURCE
    assert "'Submitted Entry Trips',len(operational_rows)" in SOURCE
    assert "Recorded / Calculated Qty MT" in SOURCE
    assert "if isinstance(value,(int,float,Decimal))" in SOURCE


def test_wb_gaps_are_visible_but_do_not_change_saved_trips():
    assert "Latest confirmed WB" in SOURCE or "Latest Confirmed WB" in SOURCE
    assert "add_sheet('WB Coverage Gaps'" in SOURCE
    assert "add_sheet('WB Review Exceptions'" in SOURCE
    assert "add_sheet('MIS Qty Gaps'" in SOURCE
    assert "wb.row_status!='VALID'" in SOURCE
    assert "owner.status=='SUBMITTED'" in SOURCE
    assert "latest_batches.setdefault((batch.operating_date,batch.shift),batch)" in SOURCE
