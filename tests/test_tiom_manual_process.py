import unittest
from types import SimpleNamespace

from app.services.tiom_manual_process import manual_lump_process_codes, manual_process_codes


def obj(id, name=None):
    return SimpleNamespace(product_id=id, name=name or id,
                           location_id=id, location_name=name or id,
                           location_type="")


class ManualLumpsFlowTests(unittest.TestCase):
    def test_screen_to_crusher_no_wb_is_both_screen_output_and_feed(self):
        codes = manual_lump_process_codes(obj("P-LMP", "Lumps"),
                                          obj("MSP3", "MSP-3"),
                                          obj("Crusher feed"))
        self.assertEqual(codes, ("LUMPS_FROM_SCREEN", "LUMPS_FEED_TO_CRUSHER", "CRUSHER_FEED"))

    def test_screen_to_stock_during_breakdown_is_not_crusher_feed(self):
        codes = manual_lump_process_codes(obj("P-LMP", "Lumps"),
                                          obj("MSP3", "MSP-3"),
                                          obj("S3", "Stock S3"))
        self.assertEqual(codes, ("LUMPS_FROM_SCREEN", "LUMPS_SHIFTED_TO_STOCK"))

    def test_stock_to_crusher_is_rehandling_and_not_new_screen_production(self):
        codes = manual_lump_process_codes(obj("P-LMP", "Lumps"),
                                          obj("ROM STOCK"),
                                          obj("Crusher feed"))
        self.assertIn("LUMPS_TO_CRUSHER_FROM_STOCK", codes)
        self.assertIn("CRUSHER_FEED", codes)
        self.assertNotIn("LUMPS_FROM_SCREEN", codes)

    def test_face_to_crusher_is_mined_lumps_not_screened_lumps(self):
        codes = manual_lump_process_codes(obj("P-LMP", "Lumps"),
                                          obj("PIT1", "Mine face RL-720"),
                                          obj("Crusher feed"))
        self.assertIn("ROM_LUMPS", codes)
        self.assertIn("CRUSHER_FEED", codes)
        self.assertNotIn("LUMPS_FROM_SCREEN", codes)

    def test_spillage_from_msp_to_msp_is_internal_recycle(self):
        codes = manual_process_codes(obj("SPILLAGE", "Spillage"),
                                     obj("MSP3", "MSP-3"), obj("MSP3", "MSP-3"))
        self.assertEqual(codes, ("SPILLAGE_RECYCLE_MSP",))
        self.assertNotIn("MSP_FEED", codes)

    def test_recovered_spillage_from_stock_is_external_msp_feed(self):
        codes = manual_process_codes(obj("SPILLAGE", "Spillage"),
                                     obj("SPILL STOCK"), obj("MSP-3"))
        self.assertIn("SPILLAGE_FROM_STOCK", codes)
        self.assertIn("MSP_FEED", codes)
        self.assertNotIn("SPILLAGE_RECYCLE_MSP", codes)

    def test_spillage_to_crusher(self):
        codes = manual_process_codes(obj("SPILLAGE", "Spillage"),
                                     obj("MSP3", "MSP-3"), obj("Crusher"))
        self.assertIn("SPILLAGE_TO_CRUSHER", codes)
        self.assertIn("CRUSHER_FEED", codes)

    def test_face_rom_direct_to_crusher(self):
        codes = manual_process_codes(obj("ROM", "ROM"),
                                     obj("PIT-1", "ROM Face RL-710"),
                                     obj("Crusher Feed"))
        self.assertIn("ROM", codes)
        self.assertIn("ROM_FEED_TO_CRUSHER", codes)
        self.assertIn("CRUSHER_FEED", codes)
        self.assertNotIn("ROM_REHANDLED", codes)

    def test_stock_rom_to_crusher_not_new_rom_production(self):
        codes = manual_process_codes(obj("ROM", "ROM"),
                                     obj("ROM STOCK"),
                                     obj("Crusher Feed"))
        self.assertIn("ROM_REHANDLED", codes)
        self.assertIn("ROM_STOCK_TO_CRUSHER", codes)
        self.assertIn("CRUSHER_STOCK_FEED", codes)
        self.assertNotIn("ROM", codes)

    def test_face_rom_via_msp_and_stock(self):
        screen = manual_process_codes(obj("ROM", "ROM"),
                                      obj("PIT1", "ROM Face"), obj("MSP-3"))
        stock = manual_process_codes(obj("ROM", "ROM"),
                                     obj("PIT1", "ROM Face"), obj("STOCK S2"))
        self.assertIn("MSP_FEED", screen)
        self.assertNotIn("CRUSHER_FEED", screen)
        self.assertIn("ROM_STOCK_YARD", stock)

    def test_lumps_face_to_crusher_is_mine_lumps(self):
        codes = manual_process_codes(obj("ROM-LUMPS", "Lumps"),
                                     obj("PIT1", "Mine Face"), obj("Crusher"))
        self.assertIn("ROM_LUMPS", codes)
        self.assertIn("ROM_FEED_TO_CRUSHER", codes)
        self.assertNotIn("LUMPS_FROM_SCREEN", codes)

    def test_clo_5_18_is_not_aliased_to_manual_lumps(self):
        self.assertEqual(manual_lump_process_codes(
            obj("P-CLO", "CLO 5-18"), obj("MSP3"), obj("Crusher feed")), ())


if __name__ == "__main__":
    unittest.main()
