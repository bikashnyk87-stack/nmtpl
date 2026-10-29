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
from test_tiom_despatch_http_flow import client


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
            {"permit_no": "L102604670", "buyer": "AMNS", "destination": "DABUNA", "material": "SCREENED FINES",
             "grade_percent": "60.79", "permit_qty": "100",
             "amns_trips": 1, "amns_mt": "31.251", "balance_mt": "68.749"},
            {"permit_no": "L102604671", "buyer": "AMNS", "destination": "DABUNA", "material": "SCREENED FINES",
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
    assert "CUMULATIVE" not in wb.sheetnames
    ws = wb["28.10.26"]
    assert ws["B2"].value.startswith("AMIPL DISPATCH DETAILS")
    assert ws["B31"].value == "CUMULATIVE DISPATCH FOR THE MONTH OF OCTOBER-2026"
    assert ws["O36"].value == 2
    assert ws["P36"].value == 61.0
    assert ws["CP37"].value.startswith("=SUM(")
    assert ws.oddHeader.left.text == "&BNMTPL | TIOM&B"
    assert totals["trips"] == 2 and totals["quantityMt"] == 61.0
    wb.close()


def test_source_saraikela_not_rejected_or_overwritten_as_old_chandil():
    """An AMNS-approved source label may differ from the old client matrix."""
    api, engine, old = client()
    try:
        _seed(engine)
        with Session(engine) as db:
            dna = db.get(mod.DespatchTrip, "L102604671/1")
            dna.buyer = "DNA MINERALS PVT LTD"
            dna.destination = "Chandil"
            dna.material_grade = "5-18mm(60-62)"
            db.commit()
        entry = {"report_date": "2026-10-28", "permits": [
            {"permit_no": "L102604670", "buyer": "AMNS",
             "destination": "DABUNA", "material": "SCREENED FINES",
             "grade_percent": "60.79", "amns_trips": 1, "amns_mt": "31.250"},
            {"permit_no": "L102604671", "buyer": "DNA MINERALS",
             "destination": "TUIDUNGRI (SARAIKELA)", "material": "5X18",
             "grade_percent": "60.50", "amns_trips": 1, "amns_mt": "29.750"},
        ]}
        response = api.post("/api/tiom/despatch/permit-entry-batch", json=entry)
        assert response.status_code == 200, response.text
        with Session(engine) as db:
            epass = db.get(mod.DespatchTrip, "L102604671/1")
            assert epass.destination == "Chandil"  # original Gmail truth
            saved = db.scalar(select(mod.DespatchPermitDay).where(
                mod.DespatchPermitDay.permit_no == "L102604671"
            ))
            assert saved.destination == "TUIDUNGRI (SARAIKELA)"
            projected = mod._report_verified_amns(db, [epass])
            assert projected[0].destination == "TUIDUNGRI (SARAIKELA)"
            from app.services.tiom_despatch_client_layout import destination_bucket_index
            assert destination_bucket_index(projected[0]) == 44
        # Confirm expected report source for the exact date, not the legacy alias.
        exported = api.get(
            "/api/tiom/despatch/export/transporter?from_date=2026-10-28&to_date=2026-10-28"
        )
        assert exported.status_code == 200, exported.text
        wb = load_workbook(BytesIO(exported.content))
        ws = wb["28.10.26"]
        assert ws["CO29"].value.startswith("=SUM(")
        assert ws["CN28"].value == 29.750  # approved DNA Saraikela bucket
        assert ws["B31"].value == "CUMULATIVE DISPATCH FOR THE MONTH OF OCTOBER-2026"
        wb.close()
    finally:
        mod.get_user, mod.require, mod.csrf = old
        engine.dispose()
