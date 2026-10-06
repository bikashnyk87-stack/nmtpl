import unittest
from decimal import Decimal
from types import SimpleNamespace

from app.services.tiom_erp import wb_report_contributions, allocate_blended_crusher_output


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
    def test_clo_10_40_to_crusher_is_old_stock_blend_not_fresh_product(self):
        codes = contribution_codes(wb(
            "CLO 10-40 mm+58%-60%FeScr.Thakurani",
            "MSP-3",
            "CRUSHER PLANT",
            "261.1",
        ))
        self.assertIn("OLD_STOCK_BLEND_10_40", codes)
        self.assertIn("PRODUCT_REHANDLED", codes)
        self.assertIn("CRUSHER_BLEND_FEED", codes)
        self.assertIn("CRUSHER_FEED", codes)
        self.assertNotIn("LUMPS_FROM_SCREEN", codes)
        self.assertNotIn("LUMPS_FEED_TO_CRUSHER", codes)
        self.assertNotIn("CRUSHER_5_18", codes)

    def test_real_msp_lumps_to_crusher_remain_fresh_intermediate(self):
        codes = contribution_codes(wb("LUMPS", "MSP-3", "CRUSHER PLANT", "120"))
        self.assertIn("LUMPS_FROM_SCREEN", codes)
        self.assertIn("LUMPS_FEED_TO_CRUSHER", codes)
        self.assertIn("CRUSHER_FEED", codes)
        self.assertNotIn("OLD_STOCK_BLEND_10_40", codes)

    def test_spillage_to_same_msp_is_recycle(self):
        codes = contribution_codes(wb("SPILLAGE", "MSP-4", "MSP-4", "25"))
        self.assertIn("SPILLAGE_RECYCLE_MSP", codes)
        self.assertNotIn("CRUSHER_FEED", codes)

    def test_large_spillage_to_crusher_is_fresh_intermediate_feed(self):
        codes = contribution_codes(wb("SPILLAGE", "MSP-4", "CRUSHER", "18"))
        self.assertIn("SPILLAGE_TO_CRUSHER", codes)
        self.assertIn("CRUSHER_FEED", codes)
        self.assertNotIn("CRUSHER_BLEND_FEED", codes)

    def test_blended_crusher_output_is_allocated_proportionally(self):
        fresh, blend = allocate_blended_crusher_output(900, 1000, 200)
        self.assertEqual(fresh, Decimal("720"))
        self.assertEqual(blend, Decimal("180"))

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
