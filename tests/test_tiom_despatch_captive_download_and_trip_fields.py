"""Live-like Captive download and Trip Summary field coverage regressions."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.routers import tiom_despatch as mod
from test_tiom_despatch_http_flow import client


def _epass(number, day, *, buyer="", material="", destination="", time="", permit_qty=0):
    return mod.DespatchTrip(
        epass_no=number,
        permit_no="L112600465", report_date=date.fromisoformat(day),
        buyer=buyer, destination=destination, material_grade=material,
        permit_qty=Decimal(str(permit_qty)), vehicle_no="OD09AB1234",
        transporter="TEST TRANSPORT", consignee="071813056432/AMNS",
        tare_mt=Decimal("15.000"), gross_mt=Decimal("46.125"),
        net_mt=Decimal("31.125"), dispatch_time=time,
        status="ACTIVE", source="Datewise 05-11-2026.xls / Rpt_Minrealwise",
    )


def test_captive_preflight_reports_the_same_missing_classification_as_export():
    api, engine, original = client()
    try:
        with Session(engine) as db:
            db.add(_epass("L112600465/1", "2026-11-05"))
            db.commit()
        query="?from_date=2026-11-05&to_date=2026-11-05"
        check=api.get("/api/tiom/despatch/export-check/despatch"+query)
        assert check.status_code==200
        assert check.json()["ready"] is False
        assert "Captive/Non-captive" in check.json()["message"]
        actual=api.get("/api/tiom/despatch/export/despatch"+query)
        assert actual.status_code==409
        assert "not classified" in actual.json()["detail"]
    finally:
        mod.get_user, mod.require, mod.csrf=original
        engine.dispose()


def test_captive_client_xlsx_and_trip_source_fields_with_confirmed_permit_qty():
    api, engine, original = client()
    try:
        with Session(engine) as db:
            db.add(_epass("L112600465/1", "2026-11-04", time=""))
            db.add(_epass("L112600465/2", "2026-11-05",
                          buyer="Self", destination="Dabuna",
                          material="S.Fines(60-62)", time="10:17:30:927AM"))
            db.add(mod.DespatchPermitDay(
                report_date=date(2026,11,4), permit_no="L112600465",
                buyer="Self", destination="Dabuna", material="S.Fines(60-62)",
                grade_percent="60.78", permit_qty=Decimal("8000.620"),
                review_status="CONFIRMED",
            ))
            db.commit()
        query="?from_date=2026-11-05&to_date=2026-11-05"
        for kind in ("trip","despatch"):
            ready=api.get("/api/tiom/despatch/export-check/"+kind+query)
            assert ready.status_code==200
            assert ready.json()["ready"] is True, ready.text
            out=api.get("/api/tiom/despatch/export/"+kind+query)
            assert out.status_code==200, out.text
            assert int(out.headers["content-length"])==len(out.content)
            book=load_workbook(BytesIO(out.content))
            try:
                if kind=="trip":
                    daily=book["05.11.26"]
                    assert daily["C2"].value=="Permit Qty."
                    assert daily["P2"].value=="WB Time"
                    assert daily["C3"].value==8000.62
                    assert daily["P3"].value=="10:17:30:927AM"
                    assert book["Cummulative"]["P3"].value is None
                else:
                    ws=book["DESTINATION WISE"]
                    assert "NOVEMBER-2026" in ws["A1"].value
                    assert ws["B2"].value=="DABUNA PLANT"
                    assert ws["V2"].value=="CUMMULATIVE"
                    assert ws["H7"].value==31.125  # S.Fines(60-62) captive
            finally:
                book.close()
        with Session(engine) as db:
            raw=db.scalar(select(mod.DespatchTrip).where(
                mod.DespatchTrip.epass_no=="L112600465/2"))
            assert raw.permit_qty==0   # report overlay is read-only
            assert raw.dispatch_time=="10:17:30:927AM"
    finally:
        mod.get_user, mod.require, mod.csrf=original
        engine.dispose()


def test_reports_use_true_user_clicked_excel_links_and_show_source_gaps():
    root=Path(__file__).resolve().parents[1]
    js=(root/"app/static/tiom_despatch.js").read_text(encoding="utf-8")
    html=(root/"app/static/index.html").read_text(encoding="utf-8")
    assert 'onclick="return tiomDDNativeLink(this,' in js
    assert "window.tiomDDNativeLink=(anchor,type)=>" in js
    assert "issues.tripFields.permitQty" in js
    assert "issues.tripFields.wbTime" in js
    assert "Missing WB Time must come from a detailed Date Wise" in js
    assert "captive-native-download-wb-qty-20261106" in html
