import unittest
from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace as Row

from app.services.tiom_erp import wb_report_contributions
from app.services.haulage_kpis import reporting_hours


def facts(material, source, destination='STACK3'):
    return dict(wb_report_contributions(Row(
        net_kg=Decimal('40000'), material_code='', material_name=material,
        source_raw=source, destination_raw=destination)))


class ProductionTests(unittest.TestCase):
    def test_rehandled_10_40_is_not_crusher_518(self):
        self.assertEqual(facts('CLO 10-40 mm+58%-60%FeScr.Thakurani',
                               'RH/Q2/S14 STAC', 'MSP 10/40 STOC'),
                         {'OTHER_PRODUCT_MOVEMENT': Decimal('40')})

    def test_screen_clo_is_not_crusher_output(self):
        self.assertIn('SCREEN_5_18', facts('CLO 5-18 mm', 'MSP-3', 'S18'))

    def test_crusher_final_output(self):
        self.assertIn('CRUSHER_5_18', facts('CLO 5-18 mm', 'CRUSHER PLANT', 'S18'))
        self.assertIn('CRUSHER_FINES', facts('Fines 0-10 mm', 'CRUSHER PLANT'))

    def test_client_stock_exclusion_does_not_depend_on_fe_grade(self):
        for grade in ('58%-60%', '60%-62%'):
            result = facts('Fines 0-10 mm+'+grade+'FeScr.Thakurani', 'PA SRF FINES')
            self.assertIn('PROJECT_AREA_FINES_TO_STACK', result)
            self.assertNotIn('SCREEN_FINES', result)

    def test_transfer_and_unknown_source_are_not_new_production(self):
        self.assertNotIn('SCREEN_FINES', facts('Fines 0-10 mm', 'S3', 'S4'))
        self.assertNotIn('SCREEN_FINES', facts('Fines 0-10 mm', 'MSP-3', 'CRUSHER PLANT'))

    def test_rom_baseline(self):
        self.assertEqual(facts('ROM Thakurani', 'QUARRY RL-820', 'MSP-3'), {'ROM':Decimal('40')})

    def test_non_positive_weight_is_excluded(self):
        for weight in (0, -100):
            self.assertEqual(wb_report_contributions(Row(net_kg=Decimal(weight))), [])


class ReportingHoursTests(unittest.TestCase):
    day = date(2026, 10, 5)
    a = Row(start_time=time(5), end_time=time(13))
    c = Row(start_time=time(21), end_time=time(5))

    def test_full_shift_includes_idle_hours(self):
        hours = reporting_hours(self.day,self.day,[self.a],datetime(2026,10,6,tzinfo=timezone.utc))
        self.assertEqual(hours,8)
        self.assertEqual(129/hours,16.125)

    def test_current_shift_uses_elapsed_time(self):
        self.assertEqual(reporting_hours(self.day,self.day,[self.a],datetime(2026,10,5,7,30,tzinfo=timezone.utc)),2.5)

    def test_overnight_and_future_shift(self):
        self.assertEqual(reporting_hours(self.day,self.day,[self.c],datetime(2026,10,6,2,tzinfo=timezone.utc)),5)
        self.assertEqual(reporting_hours(self.day,self.day,[self.c],datetime(2026,10,5,20,tzinfo=timezone.utc)),0)

    def test_overlaps_and_multiple_days(self):
        self.assertEqual(reporting_hours(self.day,date(2026,10,6),[self.a,self.a],datetime(2026,10,7,tzinfo=timezone.utc)),16)

    def test_missing_shift_master_is_unavailable(self):
        self.assertIsNone(reporting_hours(self.day,self.day,[],datetime(2026,10,7,tzinfo=timezone.utc)))


class LeadMasterTests(unittest.TestCase):
    def test_inactive_route_and_invalid_distance_do_not_resolve(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.db import Base
        from app.site_models import TiomRouteMaster, TiomLeadDistance
        from app.routers.webapp import _tiom_resolve_lead
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            route=TiomRouteMaster(route_id='r',route_name='route',source_location_id='src',
                destination_location_id='dst',route_mode='WITH_WB',lead_basis='BENCH_RL',active=False)
            lead=TiomLeadDistance(lead_id='l',source_location_id='src',destination_location_id='dst',
                route_mode='WITH_WB',bench_rl_m=820,lead_km=Decimal('2'),active=True)
            db.add_all([route,lead]); db.flush()
            def resolve():
                return _tiom_resolve_lead(db,'src',820,'dst','WITH_WB',True)
            self.assertEqual(resolve()['status'],'ROUTE_INACTIVE')
            route.active=True; lead.lead_km=0; db.flush()
            self.assertEqual(resolve()['status'],'INVALID_LEAD')
            route.lead_basis='FIXED'; route.fixed_lead_km=None; db.flush()
            self.assertEqual(resolve()['status'],'FIXED_LEAD_NOT_CONFIGURED')
            route.fixed_lead_km=Decimal('1.5'); db.flush()
            self.assertEqual(resolve()['leadKm'],Decimal('1.5'))


class DashboardIntegrationTests(unittest.TestCase):
    def test_forms_do_not_duplicate_wb_and_lead_rates_require_complete_coverage(self):
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from app.db import Base
        from app.models import ShiftMaster, WbImportBatch, WbMovement
        from app.site_models import (TiomRouteMaster, TiomMisReport, TiomMisTripRow,
                                     TiomMisTripDetail, TiomMisReconciliation)
        from app.routers.webapp import dashboard_desk
        from app.services.time_context import TZ
        engine=create_engine('sqlite://')
        Base.metadata.create_all(engine)
        day=date(2020,1,1)
        stamp=datetime(2020,1,1,6,tzinfo=TZ)
        with Session(engine) as db:
            db.add(ShiftMaster(shift='A',start_time=time(5),end_time=time(13),scheduled_hours=8,active=True))
            db.add(WbImportBatch(batch_id='b',operating_date=day,shift='A',file_name='test',file_hash='test',status='CONFIRMED',confirmed_at=stamp))
            for key,material,source,dest in [('1','ROM','PIT RL-820','MSP-3'),('2','Fines 0-10','MSP-3','S3')]:
                db.add(WbMovement(movement_key=key,batch_id='b',operating_date=day,shift='A',movement_no=key,
                    vehicle_raw='T1',material_name=material,source_raw=source,destination_raw=dest,
                    tare_kg=20000,gross_kg=60000,net_kg=40000,weigh_at=stamp,row_status='VALID'))
            db.commit()
            user=Row(admin=True,login_id='test',shifts='ALL')
            params={'mode':'CUSTOM','fromDate':'2020-01-01','toDate':'2020-01-01','shift':'A'}
            def dashboard():
                return dashboard_desk(db,user,params)
            result=dashboard()
            self.assertEqual(result['kpis']['haulageTrips'],2)
            self.assertEqual(result['kpis']['tripsPerHour'],0.25)
            self.assertIsNone(result['production']['crusherFeedMt'])
            routes=list(db.scalars(select(TiomRouteMaster)))
            self.assertEqual(len(routes),2)
            for route in routes:
                route.lead_basis='FIXED'; route.fixed_lead_km=2
            db.flush()
            self.assertEqual(dashboard()['kpis']['tripKmPerHour'],0.5)
            routes[0].fixed_lead_km=None; db.flush()
            partial=dashboard()
            self.assertEqual(partial['kpis']['haulLeadCoveragePct'],50)
            self.assertIsNone(partial['kpis']['tripKmPerHour'])
            db.add(TiomMisReport(report_id='report',operating_date=day,shift='A',vehicle_id='T1',status='SUBMITTED',entered_by='test'))
            for n in (1,2):
                db.add(TiomMisTripRow(row_id=str(n),report_id='report',row_no=n,material_raw='OB',loading_at=stamp,unloading_at=stamp))
                db.add(TiomMisTripDetail(row_id=str(n),calculated_qty_mt=40))
            db.add(TiomMisReconciliation(reconciliation_id='rec',row_id='1',wb_movement_key='1',match_status='MATCHED',reconciled_by='test'))
            db.flush()
            combined=dashboard()
            self.assertEqual(combined['kpis']['haulageTrips'],3)
            self.assertEqual(combined['production']['romInputMt'],40)
            self.assertEqual(combined['production']['finalProductionMt'],40)
            self.assertEqual(combined['kpis']['haulageReportingHours'],8)


if __name__ == '__main__':
    unittest.main()
