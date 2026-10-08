import unittest
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Location
from app.site_models import TiomLeadDistance, TiomRouteMaster
from app.routers.webapp import _tiom_area_key, _tiom_resolve_lead


class TiomMasterLeadFallbackTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine, tables=[
                Location.__table__, TiomRouteMaster.__table__,
                TiomLeadDistance.__table__,
            ],
        )
        self.db = Session(self.engine)
        for key in ["3HA/RL-840", "3_HA", "MSP-3", "4_HA"]:
            self.db.add(Location(location_id=key, location_name=key, active=True))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_master(self, source="3_HA", mode="WITH_WB", bench=840, km="2.500"):
        self.db.add(TiomRouteMaster(
            route_id=f"{source}|MSP-3|{mode}", route_name="Approved route",
            source_location_id=source, destination_location_id="MSP-3",
            route_mode=mode, lead_basis="BENCH_RL", active=True,
        ))
        self.db.add(TiomLeadDistance(
            lead_id=f"{source}|{bench}|MSP-3|{mode}",
            source_location_id=source, bench_rl_m=bench,
            destination_location_id="MSP-3", route_mode=mode,
            lead_km=Decimal(km), active=True,
        ))
        self.db.commit()

    def test_recognised_area_is_normalised_but_unrelated_names_are_not(self):
        self.assertEqual(_tiom_area_key("3HA/RL-840"), "3HA")
        self.assertEqual(_tiom_area_key("3_HA"), "3HA")
        self.assertEqual(_tiom_area_key("15-HA / RL-730"), "15HA")
        self.assertIsNone(_tiom_area_key("BGA/RL-840"))

    def test_bench_location_resolves_to_one_approved_area_master(self):
        self.add_master()
        result = _tiom_resolve_lead(
            self.db, "3HA/RL-840", 840, "MSP-3",
            "WITH_WB", wb_linked=True)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["leadKm"], Decimal("2.500"))
        self.assertEqual(result["masterSourceLocationId"], "3_HA")

    def test_wrong_bench_does_not_receive_a_guessed_distance(self):
        self.add_master()
        result = _tiom_resolve_lead(
            self.db, "3HA/RL-840", 850, "MSP-3",
            "WITH_WB", wb_linked=True)
        self.assertIsNone(result["leadKm"])

    def test_different_wb_mode_is_not_substituted(self):
        self.add_master(mode="WITH_WB")
        result = _tiom_resolve_lead(
            self.db, "3HA/RL-840", 840, "MSP-3",
            "WITHOUT_WB", wb_linked=False)
        self.assertIsNone(result["leadKm"])

    def test_same_area_conflicting_master_routes_remain_unresolved(self):
        self.db.add(Location(location_id="3HA", location_name="3HA", active=True))
        self.db.commit()
        self.add_master(source="3_HA", km="2.500")
        self.add_master(source="3HA", km="3.250")
        result = _tiom_resolve_lead(
            self.db, "3HA/RL-840", 840, "MSP-3",
            "WITH_WB", wb_linked=True)
        self.assertEqual(result["status"], "AMBIGUOUS_AREA_ROUTE")
        self.assertIsNone(result["leadKm"])


if __name__ == "__main__":
    unittest.main()
