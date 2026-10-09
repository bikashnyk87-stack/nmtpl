from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class TiomSavedReconciliationTests(unittest.TestCase):
    def test_backend_has_period_reconciliation_and_excel_export(self):
        api=(ROOT/'app'/'routers'/'webapp.py').read_text('utf-8')
        for term in (
            'def _tiom_mis_reconciliation_snapshot',
            "def get_tiom_mis_reconciliation",
            "/tiom/mis-reconciliation-export.xlsx",
            "'Trip Details'",
            "'WB Reconciliation'",
            "'Saved Report Audit'",
            "'siblingReports'",
            "'SUPERSEDED_WB_LINK'",
            "'LINKED_TO_DRAFT'",
        ):
            self.assertIn(term,api)

    def test_saved_reports_ui_has_export_reconciliation_and_tripper_switcher(self):
        ui=(ROOT/'app'/'static'/'tiom_phase1.js').read_text('utf-8')
        for term in (
            'SAVED DRIVER SHIFT REPORTS & RECONCILIATION',
            'Export Reconciliation Excel',
            'getTiomMisReconciliation',
            'Trip-level Reconciliation',
            'Select another Tripper / Report',
            'backToSavedReports',
            'View Trips',
        ):
            self.assertIn(term,ui)

    def test_phase1_cache_bust_is_current(self):
        html=(ROOT/'app'/'static'/'index.html').read_text('utf-8')
        self.assertIn('tiom_phase1.js?v=tiom-field-r28',html)


if __name__=='__main__':
    unittest.main()
