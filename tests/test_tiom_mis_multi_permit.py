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
            assert all(x.buyer == "Self" and x.destination.casefold() == "dabuna" for x in source)
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


def test_legacy_confirmed_material_band_without_numeric_grade_can_export():
    """Legacy historical MIS confirmation did not store a separate Grade %."""
    api, engine, old = client()
    try:
        with Session(engine) as db:
            db.add(mod.DespatchTrip(
                epass_no="HIST-1", permit_no="OLD-LEGACY", report_date=date(2026, 10, 27),
                net_mt=Decimal("31.850"), status="ACTIVE",
                buyer="Self", destination="Dabuna",
                material_grade="S.Fines(60-62)", transporter="TEST TRANSPORT",
            ))
            db.add(mod.DespatchPermitDay(
                permit_no="OLD-LEGACY", report_date=date(2026, 10, 27),
                buyer="Self", destination="Dabuna", material="S.Fines(60-62)",
                grade_percent="", reported_trips=1, reported_mt=Decimal("31.850"),
                review_status="CONFIRMED",
            ))
            db.commit()
        response = api.get(
            "/api/tiom/despatch/export-check/transporter"
            "?from_date=2026-10-27&to_date=2026-10-27"
        )
        assert response.status_code == 200, response.text
        assert response.json()["ready"] is True
    finally:
        mod.get_user, mod.require, mod.csrf = old
        engine.dispose()


def test_28_oct_approved_image_prefills_all_four_correctly_without_mutating_ledger():
    """Previously confirmed Chandil aliases must not displace the supplied AMNS image."""
    api, engine, old = client()
    approved = mod._APPROVED_AMNS_OCT28
    try:
        with Session(engine) as db:
            for permit, (buyer, destination, material, grade, qty, trips, mt, balance) in approved.items():
                # Split exact source MT over the E-Pass count, never round away a trip.
                per = (mt / Decimal(trips)).quantize(Decimal(".001"))
                for i in range(trips):
                    weight = per if i < trips-1 else mt - per * (trips-1)
                    db.add(mod.DespatchTrip(
                        epass_no=f"{permit}/{i+1}", permit_no=permit,
                        report_date=date(2026, 10, 28), net_mt=weight,
                        status="ACTIVE", buyer="Self" if buyer=="AMNS" else
                        ("DNA MINERALS PVT LTD" if buyer=="DNA MINERALS" else "S N N MINERALS PRIVATE LIMITED"),
                        destination="Dabuna" if buyer=="AMNS" else "Chandil",
                        material_grade="S.Fines(60-62)" if buyer=="AMNS" else "5-18mm(60-62)",
                        transporter="TEST TRANSPORT",
                    ))
                db.add(mod.DespatchPermitDay(
                    permit_no=permit, report_date=date(2026, 10, 28),
                    buyer="Self" if buyer=="AMNS" else buyer,
                    destination="Dabuna" if buyer=="AMNS" else "Chandil",
                    material="S.Fines(60-62)" if buyer=="AMNS" else "5-18mm(60-62)",
                    grade_percent=grade, reported_trips=trips, reported_mt=mt,
                    review_status="CONFIRMED",
                ))
            db.commit()
        before = api.get("/api/tiom/despatch/permit-entry-prefill?report_date=2026-10-28")
        assert before.status_code == 200, before.text
        payload = before.json()
        assert payload["totalTrips"] == 400
        assert payload["totalMt"] == 12290.210
        by_permit = {p["permit_no"]: p for p in payload["permits"]}
        assert set(by_permit) == set(approved)
        assert by_permit["L102602644"]["destination"] == "TUIDUNGRI (SARAIKELA)"
        assert by_permit["L102603256"]["destination"] == "TUIDUNGRI (SARAIKELA)"
        assert by_permit["L102604670"]["material"] == "SCREENED FINES"
        assert all(p["sourceCorrection"] for p in by_permit.values())
        # GET never mutates already stored MIS or Gmail source records.
        with Session(engine) as db:
            previous = db.scalar(select(mod.DespatchPermitDay).where(
                mod.DespatchPermitDay.permit_no == "L102603256"
            ))
            assert previous.destination == "Chandil"
        rows = [
            {"permit_no": permit, "buyer": p["buyer"],
             "destination": p["destination"], "material": p["material"],
             "grade_percent": p["grade_percent"], "permit_qty": p["permit_qty"],
             "amns_trips": p["amns_trips"], "amns_mt": p["amns_mt"],
             "balance_mt": p["balance_mt"]}
            for permit, p in by_permit.items()
        ]
        saved = api.post(
            "/api/tiom/despatch/permit-entry-batch",
            json={"report_date": "2026-10-28", "permits": rows},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["verifiedTrips"] == 400
        assert saved.json()["verifiedMt"] == 12290.210
        with Session(engine) as db:
            corrected = db.scalar(select(mod.DespatchPermitDay).where(
                mod.DespatchPermitDay.permit_no == "L102603256"
            ))
            assert corrected.destination == "TUIDUNGRI (SARAIKELA)"
            source = db.get(mod.DespatchTrip, "L102603256/1")
            assert source.destination == "Chandil"
    finally:
        mod.get_user, mod.require, mod.csrf = old
        engine.dispose()


def test_broken_legacy_permit_has_one_click_repair_and_other_permits_unchanged():
    """A report failure should provide a link to correct exactly one permit."""
    api, engine, old = client()
    try:
        with Session(engine) as db:
            for num, material in [("L102604460", "S.Fines(60-62)"),
                                  ("OTHER-27", "C.Fines(60-62)")]:
                db.add(mod.DespatchTrip(
                    epass_no=num + "/1", permit_no=num,
                    report_date=date(2026, 10, 27), status="ACTIVE",
                    buyer="Self", destination="Dabuna", material_grade=material,
                    transporter="TEST TRANSPORT", net_mt=Decimal("31.250"),
                ))
                db.add(mod.DespatchPermitDay(
                    report_date=date(2026, 10, 27), permit_no=num,
                    buyer="Self", destination="Dabuna",
                    material="UNKNOWN" if num=="L102604460" else material,
                    grade_percent="", reported_trips=1, reported_mt=Decimal("31.250"),
                    review_status="CONFIRMED",
                ))
            db.commit()
        check = api.get(
            "/api/tiom/despatch/export-check/transporter"
            "?from_date=2026-10-27&to_date=2026-10-27"
        )
        assert check.status_code == 200, check.text
        assert check.json()["ready"] is False
        assert check.json()["fixPermit"] == "L102604460"
        assert check.json()["fixDate"] == "2026-10-27"
        source = api.get(
            "/api/tiom/despatch/permit-entry-prefill?report_date=2026-10-27"
        )
        assert source.status_code == 200, source.text
        assert "S.Fines(60-62)" in source.json()["materialOptions"]
        corrected = api.post("/api/tiom/despatch/permit-entry-one", json={
            "report_date": "2026-10-27", "permit": {
                "permit_no": "L102604460", "buyer": "Self",
                "destination": "Dabuna", "material": "S.Fines(60-62)",
                "grade_percent": "", "amns_trips": 1, "amns_mt": "31.250",
            },
        })
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["tripsVerified"] == 1
        with Session(engine) as db:
            repaired = db.scalar(select(mod.DespatchPermitDay).where(
                mod.DespatchPermitDay.permit_no == "L102604460"
            ))
            other = db.scalar(select(mod.DespatchPermitDay).where(
                mod.DespatchPermitDay.permit_no == "OTHER-27"
            ))
            assert repaired.material == "S.Fines(60-62)"
            assert repaired.grade_percent == ""
            assert other.material == "C.Fines(60-62)"
            assert db.get(mod.DespatchTrip, "L102604460/1").material_grade == "S.Fines(60-62)"
            audit = db.scalars(select(mod.DespatchAudit).where(
                mod.DespatchAudit.action == "MIS_PERMIT_CORRECTION")).all()
            assert len(audit) == 1
        valid = api.get(
            "/api/tiom/despatch/export-check/transporter"
            "?from_date=2026-10-27&to_date=2026-10-27"
        )
        assert valid.status_code == 200 and valid.json()["ready"], valid.text
    finally:
        mod.get_user, mod.require, mod.csrf = old
        engine.dispose()


def test_single_permit_correction_checks_original_trip_quantity():
    api, engine, old = client()
    try:
        with Session(engine) as db:
            db.add(mod.DespatchTrip(
                epass_no="L102604460/1", permit_no="L102604460",
                report_date=date(2026, 10, 27), status="ACTIVE",
                buyer="Self", destination="Dabuna",
                material_grade="S.Fines(60-62)", transporter="T",
                net_mt=Decimal("31.250"),
            ))
            db.commit()
        incorrect = api.post("/api/tiom/despatch/permit-entry-one", json={
            "report_date": "2026-10-27", "permit": {
                "permit_no": "L102604460", "buyer": "Self",
                "destination": "Dabuna", "material": "S.Fines(60-62)",
                "amns_trips": 1, "amns_mt": "30.000",
            }
        })
        assert incorrect.status_code == 422
        with Session(engine) as db:
            assert db.scalars(select(mod.DespatchPermitDay)).all() == []
            assert db.scalars(select(mod.DespatchAudit)).all() == []
    finally:
        mod.get_user, mod.require, mod.csrf = old
        engine.dispose()
