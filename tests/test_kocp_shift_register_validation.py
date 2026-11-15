"""KOCP Coal register and OB paper-card workflow regression controls."""
from pathlib import Path
import pytest
from fastapi import HTTPException

from app.routers.kocp_shift_register import (
    validate_register_lines, validate_meter_pair, source_trip_total
)


def test_coal_register_counts_aggregate_not_input_rows():
    values=[8,6,6,4,8,9,9,6,5,3,4,5,4,6,5,1,2,3,4,4,3,3,3,1]
    assert len(values)==24
    assert sum(values)==112
    lines=validate_register_lines("COAL",[
        {"vehicleId":f"V{i}","driverId":f"D{i}","tripCount":count}
        for i,count in enumerate(values)
    ])
    assert source_trip_total(lines)==112
    assert len(lines)==24
    assert all(row["tripCount"]==values[i] for i,row in enumerate(lines))


def test_ob_card_keeps_individual_excavator_and_point():
    lines=validate_register_lines("OB",[
        {"excavatorId":"EX-1","patchCode":"K","pointCode":point}
        for point in ["2","1","1","2","2","2","1","1","5","5"]
    ])
    assert len(lines)==10
    assert source_trip_total(lines)==10
    assert [x["pointCode"] for x in lines].count("5")==2
    assert {x["tripCount"] for x in lines}=={1}


def test_ob_cannot_use_coal_aggregate_count():
    with pytest.raises(HTTPException) as e:
        validate_register_lines("OB",[
            {"excavatorId":"EX-1","patchCode":"K","pointCode":"1","tripCount":10}
        ])
    assert e.value.status_code==422


def test_coal_count_requires_positive_integer():
    for value in ["4.5", -1, 0, "abc", True]:
        with pytest.raises(HTTPException):
            validate_register_lines("COAL",[{"vehicleId":"V1","driverId":"D1","tripCount":value}])


def test_empty_or_unknown_master_ids_not_accepted_on_submission():
    with pytest.raises(HTTPException):
        validate_register_lines("COAL",[{"vehicleId":"","driverId":"D1","tripCount":2}])
    with pytest.raises(HTTPException):
        validate_register_lines("OB",[{"excavatorId":"EX1","patchCode":"","pointCode":"2"}])


def test_duplicate_mis_source_line_numbers_do_not_multiply_trips():
    with pytest.raises(HTTPException):
        validate_register_lines("OB",[
            {"lineNo":1,"excavatorId":"EX1","patchCode":"K","pointCode":"1"},
            {"lineNo":1,"excavatorId":"EX1","patchCode":"K","pointCode":"2"},
        ])


def test_meter_pair_must_be_complete_and_non_decreasing():
    assert validate_meter_pair("9424.40","9431.40")==("9424.40","9431.40")
    assert validate_meter_pair(None,None)==(None,None)
    for start,end in [(None,"20"),("20",None),("10","9"),("-2","1"),("a","2")]:
        with pytest.raises(HTTPException):
            validate_meter_pair(start,end)


def test_frontend_has_no_image_upload_or_individual_trip_time_fields():
    ui=(Path(__file__).resolve().parents[1]/"app/static/kocp_shift_register.js").read_text()
    assert "Coal Register" in ui and "OB Trip Cards" in ui
    assert "Save Draft" in ui and "Submit for Check" in ui
    assert 'type="file"' not in ui
    assert "loadingTime" not in ui
    assert "tripTime" not in ui


def test_site_trip_has_aggregate_count_with_legacy_default():
    from app.site_models import SiteTrip
    row=SiteTrip()
    assert row.trip_count is None or row.trip_count==1
    assert SiteTrip.__table__.c.trip_count.default.arg==1
