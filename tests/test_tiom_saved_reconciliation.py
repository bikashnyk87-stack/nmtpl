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

    def test_saved_reports_ui_is_entry_only_and_keeps_tripper_switcher(self):
        ui=(ROOT/'app'/'static'/'tiom_phase1.js').read_text('utf-8')
        for term in (
            'SAVED DRIVER SHIFT REPORTS',
            'Download Detailed Entry Report',
            '/api/web/tiom/mis-entry-export.xlsx',
            'No WB reconciliation is being performed.',
            'Select another Tripper / Report',
            'backToSavedReports',
            'View Trips',
        ):
            self.assertIn(term,ui)
        saved=ui[ui.index('function renderSavedReports()'):ui.index("window.toggleFactorEditor=function()")]
        self.assertNotIn('Pending',saved)
        self.assertNotIn('Matched WB',saved)
        self.assertNotIn('loadSavedReconciliation',saved)

    def test_backend_has_entry_only_export(self):
        api=(ROOT/'app'/'routers'/'webapp.py').read_text('utf-8')
        self.assertIn("/tiom/mis-entry-export.xlsx",api)
        self.assertIn("No WB reconciliation is performed here",api)
        self.assertIn("'Entry Details'",api)
        self.assertIn("'Tripper Summary'",api)
        self.assertIn("'Material Summary'",api)
        self.assertIn("'Route Summary'",api)

    def test_entry_export_uses_real_trip_time_fields(self):
        api=(ROOT/'app'/'routers'/'webapp.py').read_text('utf-8')
        block=api[api.index("def tiom_mis_entry_export"):api.index("@router.post('/rpc')")]
        self.assertNotIn('loading_raw',block)
        self.assertNotIn('unloading_raw',block)
        self.assertIn('local_time(row.loading_at)',block)
        self.assertIn('local_time(row.unloading_at)',block)
        self.assertIn('qty_index=26',block)

    def test_reload_restores_module_and_subtabs(self):
        web=(ROOT/'app'/'static'/'webapp.js').read_text('utf-8')
        phase=(ROOT/'app'/'static'/'tiom_phase1.js').read_text('utf-8')
        self.assertIn('screenStateKey',web)
        self.assertIn('sessionStorage.setItem(screenStateKey(S.boot),screen)',web)
        self.assertIn('allowedScreen(boot,saved)',web)
        self.assertIn("getUiState('PROD_TAB'",phase)
        self.assertIn("setUiState('PROD_TAB',tab)",phase)
        self.assertIn("getUiState('HSD_TAB'",phase)
        self.assertIn("setUiState('HSD_TAB',tab)",phase)

    def test_phase1_cache_bust_is_current(self):
        html=(ROOT/'app'/'static'/'index.html').read_text('utf-8')
        self.assertIn('webapp.js?v=tiom-overview-r26',html)
        self.assertIn('tiom_phase1.js?v=tiom-field-r30',html)


if __name__=='__main__':
    unittest.main()
