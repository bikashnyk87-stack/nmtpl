import unittest
from types import SimpleNamespace

from app.services.tiom_manual_process import manual_lump_process_codes


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
        self.assertEqual(codes, ("LUMPS_FROM_SCREEN",))

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

    def test_clo_5_18_is_not_aliased_to_manual_lumps(self):
        self.assertEqual(manual_lump_process_codes(
            obj("P-CLO", "CLO 5-18"), obj("MSP3"), obj("Crusher feed")), ())


if __name__ == "__main__":
    unittest.main()
