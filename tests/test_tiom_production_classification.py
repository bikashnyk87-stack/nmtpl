import unittest
from decimal import Decimal
from types import SimpleNamespace

from app.services.tiom_erp import wb_report_contributions


def wb(material, source, destination, tonnes):
    return SimpleNamespace(
        net_kg=Decimal(str(tonnes)) * Decimal("1000"),
        material_code="",
        material_name=material,
        source_raw=source,
        destination_raw=destination,
    )


def contribution_codes(row):
    return {code for code, _qty in wb_report_contributions(row)}


class TiomProductionClassificationTests(unittest.TestCase):
    def test_screen_clo_10_40_is_intermediate_not_crusher_clo(self):
        codes = contribution_codes(wb(
            "CLO 10-40 mm+58%-60%FeScr.Thakurani",
            "MSP-3",
            "CRUSHER PLANT",
            "261.1",
        ))
        self.assertIn("LUMPS_FROM_SCREEN", codes)
        self.assertIn("CRUSHER_FEED", codes)
        self.assertNotIn("CRUSHER_5_18", codes)

    def test_crusher_clo_5_18_is_crusher_output_only(self):
        codes = contribution_codes(wb(
            "CLO 5-18 mm+60%-62%FeCrus.Thakurani",
            "CRUSHER PLANT",
            "STACK8",
            "203.0",
        ))
        self.assertIn("CRUSHER_5_18", codes)
        self.assertNotIn("SCREEN_5_18", codes)
        self.assertNotIn("LUMPS_FROM_SCREEN", codes)

    def test_project_area_fines_are_rehandling_not_screen_production(self):
        codes = contribution_codes(wb(
            "Fines 0-10 mm+58%-60%FeScr.Thakurani",
            "PA SRF FINES",
            "STACK7",
            "100",
        ))
        self.assertIn("PRODUCT_REHANDLED", codes)
        self.assertIn("PROJECT_AREA_FINES_TO_STACK", codes)
        self.assertNotIn("SCREEN_FINES", codes)
        self.assertNotIn("CRUSHER_FINES", codes)

    def test_fresh_rom_to_msp_counts_rom_and_plant_feed(self):
        codes = contribution_codes(wb("ROM Thakurani", "BGA/RL-790", "MSP-3", "100"))
        self.assertIn("ROM", codes)
        self.assertIn("MSP_FEED", codes)
        self.assertNotIn("ROM_REHANDLED", codes)

    def test_near_project_area_rom_is_fresh_production_not_rehandling(self):
        codes = contribution_codes(wb("ROM Thakurani", "NEAR PROJECT AREA/RL-710", "MSP-6", "100"))
        self.assertIn("ROM", codes)
        self.assertIn("MSP_FEED", codes)
        self.assertNotIn("ROM_REHANDLED", codes)
        self.assertNotIn("PRODUCT_REHANDLED", codes)

    def test_fresh_rom_to_stock_still_counts_fresh_rom(self):
        codes = contribution_codes(wb("ROM Thakurani", "BGA/RL-790", "STACK16", "100"))
        self.assertIn("ROM", codes)
        self.assertIn("ROM_STOCK_YARD", codes)
        self.assertNotIn("ROM_REHANDLED", codes)

    def test_rom_stock_to_msp_is_rehandling_feed_not_fresh_rom(self):
        codes = contribution_codes(wb("ROM Thakurani", "ROM STOCK", "MSP-3", "100"))
        self.assertIn("ROM_REHANDLED", codes)
        self.assertIn("ROM_STOCK_TO_PLANT_FEED", codes)
        self.assertIn("MSP_FEED", codes)
        self.assertNotIn("ROM", codes)


if __name__ == "__main__":
    unittest.main()
