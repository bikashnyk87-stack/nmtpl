"""MIS multi-permit source controls and branded cumulative transporter report."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.routers import tiom_despatch as mod
from app.services.tiom_despatch_client_reports import build_client_workbook
from tests.test_tiom_despatch_http_flow import client


def _seed(engine):
    with Session(engine) as db:
        for permit, epass, mt in [
            ("L102604670", "L102604670/1", "31.250"),
            ("L102604671", "L102604671/1", "29.750"),
        ]:
            db.add(mod.DespatchTrip(
                epass_no=epass, permit_no=permit, report_date=date(2026, 10, 28),
                net_mt=Decimal(mt), status="ACTIVE", buyer="", destination="",
                material_grade="", transporter="TEST TRANSPORT",
            ))
        db.commit()


def test_date_wise_manual_multi_permit_is_atomic_and_does_not_require_image():
    api, engine, old = client()
    try:
        _seed(engine)
        r = api.get("/api/tiom/despatch/permit-entry-prefill?report_date=2026-10-28")
        assert r.status_code == 200, r.text
        prefill = r.json()
        assert len(prefill["permits"]) == 2
        assert prefill["totalTrips"] == 2
        categories = prefill["categories"]
        bucket = next(x["index"] for x in categories
                      if x["buyer"] == "Self" and x["destination"] == "Dabuna"
                      and x["material"] == "S.Fines(60-62)")
        data = {"report_date": "2026-10-28", "permits": [
            {"permit_no": "L102604670", "category_index": bucket,
             "grade_percent": "60.79", "permit_qty": "100",
             "amns_trips": 1, "amns_mt": "31.251", "balance_mt": "68.749"},
            {"permit_no": "L102604671", "category_index": bucket,
             "grade_percent": "60.79", "permit_qty": "100",
             "amns_trips": 1, "amns_mt": "22.750", "balance_mt": "77.250"},
        ]}
        bad = api.post("/api/tiom/despatch/permit-entry-batch", json=data)
        assert bad.status_code == 422 and "L102604671" in bad.text
        with Session(engine) as db:
            assert db.scalars(select(mod.DespatchPermitDay)).all() == []
            assert all(x.buyer == "" for x in db.scalars(select(mod.DespatchTrip)))
        data["permits"][1]["amns_mt"] = "29.750"
        saved = api.post("/api/tiom/despatch/permit-entry-batch", json=data)
        assert saved.status_code == 200, saved.text
        assert saved.json()["verifiedPermits"] == 2
        assert saved.json()["verifiedMt"] == 61.0
        with Session(engine) as db:
            entries = db.scalars(select(mod.DespatchPermitDay)).all()
            assert len(entries) == 2
            assert all(x.review_status == "CONFIRMED" and x.document_id is None for x in entries)
            source = db.scalars(select(mod.DespatchTrip)).all()
            assert all(x.buyer == "Self" and x.destination == "Dabuna" for x in source)
            assert sorted(x.net_mt for x in source) == [Decimal("29.750"), Decimal("31.250")]
            assert len(db.scalars(select(mod.DespatchAudit).where(
                mod.DespatchAudit.action == "MIS_PERMIT_BATCH")).all()) == 1
        assert api.post("/api/tiom/despatch/permit-entry-batch", json=data).status_code == 200
        assert api.get("/api/tiom/despatch/permit-entry-prefill?report_date=2026-10-26").status_code == 422
    finally:
        mod.get_user, mod.require, mod.csrf = old
        engine.dispose()


def test_cumulative_monthly_transporter_sheet_has_requested_heading_and_totals():
    records = [
        SimpleNamespace(epass_no="L102604670/1", report_date=date(2026, 10, 27),
                        buyer="Self", destination="Dabuna", material_grade="S.Fines(60-62)",
                        transporter="TEST TRANSPORT", net_mt=Decimal("31.250"), status="ACTIVE"),
        SimpleNamespace(epass_no="L102604670/2", report_date=date(2026, 10, 28),
                        buyer="Self", destination="Dabuna", material_grade="S.Fines(60-62)",
                        transporter="TEST TRANSPORT", net_mt=Decimal("29.750"), status="ACTIVE"),
    ]
    out, totals = build_client_workbook("transporter", records, date(2026, 10, 27),
                                        date(2026, 10, 28))
    wb = load_workbook(BytesIO(out.getvalue()))
    assert "CUMULATIVE" in wb.sheetnames
    assert wb["CUMULATIVE"]["B2"].value == (
        "CUMULATIVE DISPATCH FOR THE MONTH OF OCTOBER-2026"
    )
    assert wb["CUMULATIVE"]["O9"].value == 2
    assert wb["CUMULATIVE"]["P9"].value == 61.0
    assert wb["CUMULATIVE"]["CL9"].value.startswith("=SUM(")
    assert wb["27.10.26"]["B2"].value.startswith("AMIPL DISPATCH DETAILS")
    assert wb["CUMULATIVE"].oddHeader.left.text == "&BNMTPL | TIOM&B"
    assert totals["trips"] == 2 and totals["quantityMt"] == 61.0
    wb.close()
