from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.routers.tiom_despatch import (
    DespatchAudit, DespatchDocument, DespatchPermitDay, DespatchSender,
    DespatchTrip, _extract, _import_data, _trip,
)
from app.services.tiom_despatch_mail import DespatchEmailProcessed


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        DespatchAudit.__table__, DespatchDocument.__table__,
        DespatchPermitDay.__table__, DespatchSender.__table__,
        DespatchTrip.__table__, DespatchEmailProcessed.__table__,
    ])
    return engine


def _csv():
    return (
        "report_date,permit_no,permit_qty,buyer,epass_no,vehicle_no,transporter,"
        "destination,material_grade,stack_no,consignee,tare_mt,gross_mt,"
        "net_mt,dispatch_date,dispatch_time,status,source\n"
        "2026-10-01,L1,100,Self,L1/1,OD1,ABC,Dabuna,S.Fines(60-62),ST1,AMNS,15,45,30,2026-10-01,10:00,ACTIVE,test\n"
        "2026-10-26,L1,100,Self,L1/2,OD2,ABC,Dabuna,S.Fines(60-62),ST1,AMNS,15,47,32,2026-10-26,10:00,ACTIVE,test\n"
    ).encode()


def test_october_csv_import_is_duplicate_safe():
    engine = _engine()
    with Session(engine) as db:
        first = _import_data(db, _csv(), "october.csv", "TEST")
        assert first["ok"] and first["inserted"] == 2
        repeat = _import_data(db, _csv(), "october.csv", "TEST")
        assert repeat["ok"] and repeat["inserted"] == 0
        assert repeat["skippedExisting"] == 2
        assert db.scalar(select(func.count()).select_from(DespatchTrip)) == 2
        assert db.scalar(select(func.sum(DespatchTrip.net_mt))) == Decimal("62.000")


def test_invalid_weights_reject_full_batch():
    engine = _engine()
    with Session(engine) as db:
        bad = _csv().replace(b",15,47,32,", b",15,47,35,")
        report = _import_data(db, bad, "october.csv", "TEST")
        assert not report["ok"]
        assert report["inserted"] == 0
        assert db.scalar(select(func.count()).select_from(DespatchTrip)) == 0


def test_cumulative_sheet_not_imported_twice():
    wb = Workbook()
    ws = wb.active
    ws.title = "01.10.26"
    ws.append(["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""])
    ws.append(["Sl.No.", "Permit No.", "Permit Qty.", "Buyer Name", "E-Pass No",
               "Vehicle RegNo", "Transporter Name", "Destination", "Material/Grade",
               "Stack No.", "Consignee Name", "Tare Wt.", "Gross Wt.",
               "Net Wt.", "Date ", "Time"])
    ws.append([1, "L1", 100, "Self", "L1/1", "OD1", "ABC", "Dabuna",
               "S.Fines(60-62)", "ST1", "AMNS", 15, 45, 30, "Oct 1 2026", "10:00"])
    cumulative = wb.create_sheet("Cummulative")
    cumulative.append(["duplicated totals"])
    buf = BytesIO()
    wb.save(buf)
    parsed = _extract(buf.getvalue(), "Trip Summary Oct-26.xlsx")
    assert len(parsed) == 1
    assert parsed[0]["epass_no"] == "L1/1"


def test_grade_and_date_validation():
    from datetime import date
    candidate = {"epass_no": "L1/1", "report_date": "2026-10-01",
                 "permit_no": "L1", "gross_mt": "45", "tare_mt": "15", "net_mt": "30"}
    row = _trip(candidate)
    assert row["report_date"] == date(2026, 10, 1)
    assert row["net_mt"] == Decimal("30.000")
    candidate["net_mt"] = "31"
    try:
        _trip(candidate)
        assert False, "unreconciled weights should fail"
    except ValueError:
        pass
