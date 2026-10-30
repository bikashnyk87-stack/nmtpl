"""KOCP material normalization regressions based on supplied Coal/OB sheet formats."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.site_models import Site, SiteMaterial
from app.routers.site_material_types import (
    CATEGORIES, _as_row, _classify, _issues, _material_existing
)

HEADERS=["Code","Material Name","Material Group","Distance KM",
         "Default Unit","Billable Unit","Active"]


def test_coal_sheet_21_distance_variants_are_only_two_material_types():
    sample=[
        (None,"Reject","Reject Dump yard","1-2/1-2","MT","MT","TRUE"),
        (None,"Coal","Stock","1-2/1-2","MT","MT","TRUE"),
        (None,"Coal","Stock","1-2/3-4","MT","MT","TRUE"),
        (None,"Coal","Siding","2-3/5-6","MT","MT","TRUE"),
        (None,"Coal","Siding","4-5/5-6","MT","MT","TRUE"),
    ]
    rows=[_as_row("COAL",HEADERS,r) for r in sample]
    assert {r["materialType"] for r in rows}=={"COAL","REJECT"}
    assert all(not _issues(r) for r in rows)
    assert rows[2]["distanceRange"]=="1-2/3-4"
    assert rows[0]["originalCode"]==""


def test_ob_sheet_numeric_codes_remain_evidence_not_material_ids():
    sample=[
        (1.1,"Soft OB (Without Drilling) "," working place to Dump","0-1","CUM","CUM","TRUE"),
        (1.2,"Soft OB (Without Drilling) "," working place to Dump","1-2","CUM","CUM","TRUE"),
        (2.1,"Hard OB (With Drilling) "," working place to Dump","0-1","CUM","CUM","TRUE"),
        (2.6,"Hard OB (With Drilling) "," working place to Dump","5-6","CUM","CUM","TRUE"),
        (3," Re-handling OB  ","working place to Dump","2-3","CUM","CUM","TRUE"),
    ]
    rows=[_as_row("OB",HEADERS,r) for r in sample]
    assert {r["materialType"] for r in rows}=={"SOFT_OB","HARD_OB","REHANDLING_OB"}
    assert rows[0]["originalCode"]=="1.1"
    assert rows[-1]["originalCode"]=="3"
    assert all(not _issues(r) for r in rows)


def test_invalid_unit_or_unknown_material_are_blocked():
    bad=_as_row("OB",HEADERS,(2.1,"Hard OB (With Drilling)","Dump","2-3","MT","MT","TRUE"))
    assert any("CUM" in x for x in _issues(bad))
    unknown=_as_row("COAL",HEADERS,(None,"Mystery stone","Stock","1-2","MT","MT","TRUE"))
    assert any("Unrecognized" in x for x in _issues(unknown))


def test_safe_existing_material_reuse_and_conflict():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Site.__table__, SiteMaterial.__table__])
    with Session(engine) as db:
        db.add(Site(site_id="KOCP",site_name="KOCP",short_name="KOCP",active=True))
        db.add(SiteMaterial(site_material_id="KOCP:OLD_COAL",site_id="KOCP",code="OLD_COAL",
                            name="Coal",material_group="STOCK",default_unit="MT",active=True))
        db.flush()
        matched,problem=_material_existing(db,"COAL","COAL")
        assert matched.site_material_id=="KOCP:OLD_COAL"
        assert problem is None
        db.add(SiteMaterial(site_material_id="KOCP:HARD_OB",site_id="KOCP",code="HARD_OB",
                            name="Coal",material_group="OTHER",default_unit="MT",active=True))
        db.flush()
        matched,problem=_material_existing(db,"OB","HARD_OB")
        assert matched is None
        assert "will not be overwritten" in problem
    engine.dispose()


def test_canonical_count_is_five():
    assert len(CATEGORIES["COAL"])==2
    assert len(CATEGORIES["OB"])==3
