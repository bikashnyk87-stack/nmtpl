"""Future-dated Despatch source imports capture time and approved source Permit Qty.

A Date Wise timestamp can supply WB Time when a separate WB Time column
is absent. A source with no Permit Qty must not invent one.
"""
from app.services.tiom_despatch_source_adapters import parse_despatch_sources
from app.routers.tiom_despatch import _trip


def test_future_datewise_source_captures_embedded_wb_time_and_permit_quantity():
    source=(
        "E-Pass No,Date,Permit No,Permit Qty,Vehicle RegNo,Tare Wt,Gross Wt,Net Wt\n"
        "L112600999/1,Nov 20 2026 10:26:53:543AM,L112600999,6000.250,OD09AB1234,15,47,32\n"
    ).encode("utf-8")
    rows=parse_despatch_sources(source,"Datewise 20-11-2026.csv")
    assert len(rows)==1
    assert rows[0]["_role"]=="detailed"
    assert rows[0]["report_date"]=="2026-11-20"
    assert rows[0]["dispatch_time"]=="10:26:53:543AM"
    assert rows[0]["permit_qty"]=="6000.250"
    parsed=_trip(rows[0])
    assert str(parsed["permit_qty"])=="6000.250"
    assert parsed["dispatch_time"]=="10:26:53:543AM"


def test_future_datewise_source_does_not_invent_missing_permit_quantity():
    source=(
        "E-Pass No,Date,Permit No,Vehicle RegNo,Tare Wt,Gross Wt,Net Wt\n"
        "L112600999/2,Nov 20 2026 09:10:13:033AM,L112600999,OD09AB1235,15,46,31\n"
    ).encode("utf-8")
    rows=parse_despatch_sources(source,"Datewise 20-11-2026.csv")
    assert len(rows)==1
    assert rows[0]["dispatch_time"]=="09:10:13:033AM"
    assert rows[0].get("permit_qty") is None
    parsed=_trip(rows[0])
    assert parsed["permit_qty"]==0


def test_future_source_explicit_wb_time_is_preserved():
    source=(
        "E-Pass No,Date,Permit No,Permit Qty,Vehicle RegNo,Tare Wt,Gross Wt,Net Wt,WB Time\n"
        "L112600999/3,20-11-2026,L112600999,6000.250,OD09AB1236,15,46,31,11:35:40\n"
    ).encode("utf-8")
    rows=parse_despatch_sources(source,"Datewise 20-11-2026.csv")
    assert rows[0]["dispatch_time"]=="11:35:40"
    assert rows[0]["permit_qty"]=="6000.250"
