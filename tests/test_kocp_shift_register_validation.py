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


def test_ob_rows_sum_trip_counts_by_excavator_and_points():
    rows = validate_register_lines("OB", [
        {"excavatorId": "EX-1", "patchCode": "K", "pointCode": "1", "tripCount": 10},
        {"excavatorId": "EX-2", "patchCode": "K", "pointCode": "1", "tripCount": 4},
    ])
    assert [row["tripCount"] for row in rows] == [10, 4]
    assert source_trip_total(rows) == 14


@pytest.mark.parametrize("count", [0, -1, 1.5, True, 201, "²", "9" * 200])
def test_ob_rejects_invalid_trip_counts(count):
    with pytest.raises(HTTPException) as error:
        validate_register_lines("OB", [
            {"excavatorId": "EX-1", "patchCode": "K", "pointCode": "1", "tripCount": count},
        ])
    assert error.value.status_code == 422


def test_driver_is_optional_on_coal_source_lines():
    without = validate_register_lines("COAL", [{"vehicleId": "V1", "tripCount": 5}])[0]
    assert without["driverId"] == ""
    assert validate_register_lines("COAL", [{"vehicleId": "V1", "driverId": None, "tripCount": 5}])[0]["driverId"] == ""
    with pytest.raises(HTTPException):
        validate_register_lines("COAL", [{"vehicleId": "", "tripCount": 5}])


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


def test_ob_master_locations_must_match_both_route_endpoints(monkeypatch):
    from types import SimpleNamespace
    from app.routers import kocp_shift_register as registers

    locations = {"PATCH": "KOCP:SOURCE", "UNLOAD_POINT": "KOCP:DUMP"}
    monkeypatch.setattr(registers, "_code", lambda db, kind, value:
        SimpleNamespace(code_id=value, parent_location_id=locations[kind]))
    monkeypatch.setattr(registers, "_site_location_or_422", lambda db, site, location: location)
    route = SimpleNamespace(source_location_id="KOCP:SOURCE", destination_location_id="KOCP:DUMP")
    registers._ob_locations(None, route, 1, "PATCH-1", "POINT-1")
    for kind in locations:
        original = locations[kind]
        locations[kind] = "KOCP:WRONG"
        with pytest.raises(HTTPException, match="does not match"):
            registers._ob_locations(None, route, 1, "PATCH-1", "POINT-1")
        locations[kind] = original


@pytest.mark.parametrize("paper_codes", [True, False])
def test_master_backed_coal_and_ob_save_reopen_submit_and_post(monkeypatch, paper_codes):
    from datetime import date, time
    from types import SimpleNamespace

    from sqlalchemy import create_engine, event, select
    from sqlalchemy.orm import Session

    from app.db import Base
    from app.models import Equipment, Person
    from app.routers import kocp_shift_register as registers
    from app.site_models import (
        EquipmentSiteAssignment, PersonSiteAssignment, Site, SiteLocation, SiteMaterial,
        SiteMovementRoute, SiteOperationalCode, SiteShift, SiteShiftTripCardLine, SiteTrip,
    )

    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enforce_fk(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    day = date(2026, 11, 15)
    user = SimpleNamespace(login_id="ENTRY", admin=False)
    monkeypatch.setattr(registers, "_auth", lambda *args: user)
    with Session(engine) as db:
        db.add_all([
            Site(site_id="KOCP", site_name="KOCP", short_name="KOCP"),
            SiteShift(site_id="KOCP", shift="A", start_time=time(5), end_time=time(13), scheduled_hours=8),
            SiteShift(site_id="KOCP", shift="B", start_time=time(13), end_time=time(21), scheduled_hours=8),
            Person(employee_id="D1", name="Test Driver", role="TIPPER DRIVER"),
            Person(employee_id="D2", name="Future Driver", role="DRIVER"),
            Person(employee_id="D3", name="Test Helper", role="HELPER"),
            PersonSiteAssignment(employee_id="D1", site_id="KOCP", effective_from=day),
            PersonSiteAssignment(employee_id="D2", site_id="KOCP", effective_from=date(2026, 11, 16)),
            PersonSiteAssignment(employee_id="D3", site_id="KOCP", effective_from=day),
            Equipment(machine_id="T1", type="TIPPER", group="COAL OB"),
            Equipment(machine_id="E1", type="EXCAVATOR", group="OB"),
            Equipment(machine_id="L1", type="LOADER", group="COAL"),
            EquipmentSiteAssignment(machine_id="T1", site_id="KOCP", effective_from=day),
            EquipmentSiteAssignment(machine_id="E1", site_id="KOCP", effective_from=day),
            EquipmentSiteAssignment(machine_id="L1", site_id="KOCP", effective_from=day),
            SiteLocation(site_location_id="KOCP:FACE", site_id="KOCP", code="FACE", name="Test Face"),
            SiteLocation(site_location_id="KOCP:DUMP", site_id="KOCP", code="DUMP", name="Test Dump"),
            SiteOperationalCode(code_id="KOCP:PATCH:P", site_id="KOCP", code_kind="PATCH",
                                code="P", name="Paper patch", parent_location_id="KOCP:FACE"),
            SiteOperationalCode(code_id="KOCP:UNLOAD_POINT:U", site_id="KOCP", code_kind="UNLOAD_POINT",
                                code="U", name="Paper unloading point", parent_location_id="KOCP:DUMP"),
        ])
        for kind, unit in [("COAL", "MT"), ("OB", "CUM")]:
            db.add(SiteMaterial(site_material_id=kind, site_id="KOCP", code=kind, name=kind, default_unit=unit))
            db.add(SiteMovementRoute(route_id=kind, site_id="KOCP", movement_kind=kind,
                                     route_group=kind, category=kind, destination_label="Test Dump",
                                     source_location_id="KOCP:FACE", destination_location_id="KOCP:DUMP",
                                     distance_range="1-2"))
        db.flush()
        if not paper_codes:
            for code in db.scalars(select(SiteOperationalCode)).all():
                db.delete(code)
        db.commit()
        assert [row["id"] for row in registers.list_drivers(None, day, db)] == ["D1"]

        for kind, count in [("OB", 8), ("COAL", 5)]:
            user.login_id = "ENTRY"
            payload = {"clientKey": f"master-test-{kind}", "kind": kind, "operatingDate": day.isoformat(),
                       "shift": "A", "materialId": kind, "routeId": kind, "declaredTotal": count}
            if kind == "OB":
                point_fields = ({"patchCode": "P", "pointCode": "U"} if paper_codes else
                                {"sourceLocationId": "KOCP:FACE", "destinationLocationId": "KOCP:DUMP"})
                payload.update(vehicleId="T1", driverId="D1", lines=[{"excavatorId": "E1", "tripCount": count, **point_fields}])
            else:
                payload["lines"] = [{"vehicleId": "T1", "driverId": "D1", "excavatorId": "L1", "tripCount": count}]
            draft = registers.create_card(payload, None, db)
            card_id = draft["cardId"]
            assert registers.create_card(payload, None, db)["idempotent"]
            assert registers.get_card(card_id, None, db)["tripCount"] == count
            if kind == "OB":
                draft_line = db.scalar(select(SiteShiftTripCardLine).where(
                    SiteShiftTripCardLine.card_id == card_id))
                assert draft_line.source_location_id == "KOCP:FACE"
                assert draft_line.destination_location_id == "KOCP:DUMP"
                assert draft_line.patch_code_id == ("KOCP:PATCH:P" if paper_codes else None)
                assert draft_line.unload_code_id == ("KOCP:UNLOAD_POINT:U" if paper_codes else None)
            submitted = registers.submit_card(card_id, {"expectedVersion": draft["version"]}, None, db)
            queue = registers.review_queue(None, db)
            pending = next((item for item in queue["items"] if item["cardId"] == card_id), None)
            assert pending is not None
            assert pending["kind"] == kind and pending["tripCount"] == count
            assert queue["totalPending"] >= 1
            user.login_id = "CHECKER"
            decision = {"action": "VERIFY", "expectedVersion": submitted["version"]}
            assert registers.decide_card(card_id, decision, None, db)["status"] == "VERIFIED"
            assert registers.decide_card(card_id, decision, None, db)["idempotent"]
            assert all(item["cardId"] != card_id for item in registers.review_queue(None, db)["items"])

        # Fully verify driver-less Coal and OB records on a distinct shift.
        for kind, count in [("COAL", 6), ("OB", 9)]:
            user.login_id = "ENTRY"
            payload = {"clientKey": f"driver-optional-{kind}", "kind": kind,
                       "operatingDate": day.isoformat(), "shift": "B",
                       "materialId": kind, "routeId": kind, "declaredTotal": count}
            if kind == "OB":
                points = ({"patchCode": "P", "pointCode": "U"} if paper_codes else
                          {"sourceLocationId": "KOCP:FACE", "destinationLocationId": "KOCP:DUMP"})
                payload.update(vehicleId="T1", driverId="", lines=[
                    {"excavatorId": "E1", "tripCount": count, **points}])
            else:
                payload["lines"] = [{"vehicleId": "T1", "tripCount": count}]
            draft = registers.create_card(payload, None, db)
            assert draft["driverId"] == ""
            assert draft["lines"][0]["driverId"] == ""
            submitted = registers.submit_card(draft["cardId"], {"expectedVersion": draft["version"]}, None, db)
            user.login_id = "CHECKER"
            outcome = registers.decide_card(draft["cardId"], {"action": "VERIFY",
                                                  "expectedVersion": submitted["version"]}, None, db)
            assert outcome["status"] == "VERIFIED"
        trips = db.scalars(select(SiteTrip)).all()
        assert sorted(row.trip_count for row in trips) == [5, 6, 8, 9]
        assert sorted(row.trip_count for row in trips if row.driver_id is None) == [6, 9]
        posted_lines = db.scalars(select(SiteShiftTripCardLine)).all()
        assert {line.trip_id for line in posted_lines} == {trip.trip_id for trip in trips}
        assert {row.driver_id for row in trips} == {"D1", None}
        assert {row.source_location_id for row in trips} == {"KOCP:FACE"}
        assert {row.destination_location_id for row in trips} == {"KOCP:DUMP"}
        # Coal linked loader is retained through verification into the report grain.
        coal_posted = next(t for t in trips if t.trip_count == 5)
        assert coal_posted.loading_equipment_id == "L1"

        # Draft/returned deletion keeps an audit trail and cannot remove verified production.
        from app.site_models import SiteShiftTripCard
        for kind in ("COAL", "OB"):
            user.login_id = "ENTRY"
            payload = {"clientKey": f"cancel-draft-{kind}-NOV26", "kind": kind,
                       "operatingDate": day.isoformat(), "shift": "A",
                       "materialId": kind, "routeId": kind, "declaredTotal": 2}
            if kind == "COAL":
                payload["lines"] = [{"vehicleId": "T1", "excavatorId": "L1", "tripCount": 2}]
            else:
                p = ({"patchCode": "P", "pointCode": "U"} if paper_codes else
                     {"sourceLocationId": "KOCP:FACE", "destinationLocationId": "KOCP:DUMP"})
                payload.update(vehicleId="T1", lines=[{"excavatorId":"E1","tripCount":2,**p}])
            new = registers.create_card(payload, None, db)
            deleted = registers.cancel_card(new["cardId"],
                          {"expectedVersion":new["version"],"reason":"Incorrect paper entry"},None,db)
            assert deleted["status"] == "CANCELLED"
            assert db.get(SiteShiftTripCard,new["cardId"]).status == "CANCELLED"
            assert all(x["cardId"]!=new["cardId"] for x in registers.list_cards(None,day,kind,db))
        with pytest.raises(HTTPException) as locked:
            registers.cancel_card(coal_posted.source_record_uid.split(":")[0],
                {"expectedVersion":2,"reason":"Invalid physical card"},None,db)
        assert locked.value.status_code == 409



def test_grouped_ob_and_individual_ob_have_same_duplicate_signature():
    from types import SimpleNamespace
    from app.routers.kocp_shift_register import _source_signature

    card = SimpleNamespace(kind="OB", operating_date="2026-11-15", shift="A",
                           vehicle_id="T1", route_id="R1", material_id="M1")
    line = dict(excavator_id="E1", source_location_id="S", destination_location_id="D",
                patch_source=None, unload_source=None, route_id=None)
    assert _source_signature(card, [SimpleNamespace(**line, trip_count=8)]) == _source_signature(
        card, [SimpleNamespace(**line, trip_count=1)] * 8,
    )
