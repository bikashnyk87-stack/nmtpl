"""Regression checks for KOCP Coal and OB masters and physical-location merge."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.routers.site_routes import _distance, _extract, _identity, _issues, _physical_location
from app.site_models import Site, SiteLocation


def test_original_coal_layout_does_not_treat_group_as_source_location():
    headers=["Siding KN-4/KN-4A/TRH/ATLS", "Location Name", "Role", "Location Type",
             "Distance KM", "Latitude", "Longitude", "Active"]
    item=_extract("COAL",headers,
        ["Coal Stock","Coal StockKN-5/KN-6","Stock","UNLOADING","1-2/3-4",None,None,"TRUE"])
    assert item["group"]=="Coal Stock"
    assert item["source"]==""  # Coal's first column is a movement GROUP, not a physical source
    assert item["destination"]=="Coal StockKN-5/KN-6"
    assert item["distance"]=="1-2/3-4"
    assert _issues(item)==[]


def test_original_ob_layout_extracts_source_destination_and_category():
    headers=["From","To Location Name","Role","Location Type","Distance KM",
             "Latitude","Longitude","Active"]
    one=_extract("OB",headers,["Working Face","Dump Yard","Hard OB (With Drilling)",
                "UNLOADING","3-4",None,None,"TRUE"])
    assert one["source"]=="Working Face"
    assert one["destination"]=="Dump Yard"
    assert one["category"]=="Hard OB (With Drilling)"
    assert _issues(one)==[]
    two=dict(one,distance="4-5")
    assert _identity(one)!=_identity(two)
    assert _identity(one)==_identity(dict(one))


@pytest.mark.parametrize("bad",["1-1","2-1","-1","0-1/3","1/2","", "2-3 MT"])
def test_invalid_distance_range_rejected(bad):
    with pytest.raises(ValueError):
        _distance(bad)


def test_multiple_route_variations_share_one_physical_location():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Site.__table__, SiteLocation.__table__])
    with Session(engine) as db:
        db.add(Site(site_id="KOCP",site_name="KOCP",short_name="KOCP",active=True))
        db.flush()
        names={}
        a=_physical_location(db,"Dump Yard",names,"batch-coal")
        b=_physical_location(db," dump  yard ",names,"batch-ob")
        c=_physical_location(db,"Working Face",names,"batch-ob")
        db.flush()
        assert a.site_location_id==b.site_location_id
        assert a.site_location_id!=c.site_location_id
        saved=db.scalars(select(SiteLocation).where(SiteLocation.site_id=="KOCP")).all()
        assert len(saved)==2
    engine.dispose()
