from pathlib import Path
import re
import unittest

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


class TiomManagementUiWiringTests(unittest.TestCase):
    def test_owner_view_loads_after_all_legacy_modules(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r'<script src="([^"]+)"', html)
        names = [part.split("/")[-1].split("?")[0] for part in scripts]
        self.assertLess(names.index("workspace.js"), names.index("tiom_phase1.js"))
        self.assertLess(names.index("tiom_phase1.js"), names.index("tiom_management_ui.js"))
        self.assertLess(names.index("mechanical_erp.js"), names.index("tiom_management_ui.js"))

    def test_phase1_does_not_override_owner_render(self):
        phase1 = (STATIC / "tiom_phase1.js").read_text(encoding="utf-8")
        self.assertNotIn("window.renderHome=function()", phase1)

    def test_management_login_opens_overview(self):
        web = (STATIC / "webapp.js").read_text(encoding="utf-8")
        self.assertIn("render(boot.user.isManagement?'HOME'", web)

    def test_live_summary_present_and_operational_drilldowns_retained(self):
        owner = (STATIC / "tiom_management_ui.js").read_text(encoding="utf-8")
        dashboard = (STATIC / "workspace.js").read_text(encoding="utf-8")
        for title in (
            "Owner Overview",
            "Work achieved",
            "Owner attention",
            "Equipment performance",
            "Fuel issued by activity",
            "Plant performance",
            "Drilling & entry completeness",
            "Production flow & allocation",
            "Movement reconciliation",
            "Machine breakdown report",
            "Shift comparison",
        ):
            self.assertIn(title, owner)
        self.assertIn("window.tiomRefDetailed(d)", dashboard)
        self.assertIn("Additional detailed operational reports", dashboard)
        self.assertIn("dashboard_body", dashboard)
        self.assertIn("getDashboard(", dashboard)


if __name__ == "__main__":
    unittest.main()
