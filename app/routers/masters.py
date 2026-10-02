from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import (
    Person, Equipment, Location, Product, ShiftRotation, ShiftMaster, ActivityMaster,
    HsdTanker, VehicleAlias, LocationAlias, MaterialAlias,
)
from app.schemas import (
    PersonIn, EquipmentIn, LocationIn, ProductIn, ShiftRotationIn, ShiftMasterIn,
    ActivityIn, HsdTankerIn, VehicleAliasIn, LocationAliasIn, MaterialAliasIn,
)
from app.services.shift_rotation import resolve_rotation_shift

router = APIRouter(prefix="/api/masters", tags=["masters"])


def _upsert(db: Session, model, key_name: str, data: dict):
    key = data[key_name]
    row = db.get(model, key)
    if row is None:
        row = model(**data)
    else:
        for k, v in data.items():
            setattr(row, k, v)
    db.add(row)
    db.commit()
    return {"ok": True, key_name: key}


@router.get("/persons")
def persons(db: Session = Depends(get_db)):
    return db.execute(select(Person).order_by(Person.employee_id)).scalars().all()

@router.post("/persons")
def upsert_person(p: PersonIn, db: Session = Depends(get_db)):
    return _upsert(db, Person, "employee_id", p.model_dump())

@router.get("/equipment")
def equipment(db: Session = Depends(get_db)):
    return db.execute(select(Equipment).order_by(Equipment.machine_id)).scalars().all()

@router.post("/equipment")
def upsert_equipment(p: EquipmentIn, db: Session = Depends(get_db)):
    return _upsert(db, Equipment, "machine_id", p.model_dump())

@router.get("/locations")
def locations(db: Session = Depends(get_db)):
    return db.execute(select(Location).order_by(Location.location_id)).scalars().all()

@router.post("/locations")
def upsert_location(p: LocationIn, db: Session = Depends(get_db)):
    return _upsert(db, Location, "location_id", p.model_dump())

@router.get("/products")
def products(db: Session = Depends(get_db)):
    return db.execute(select(Product).order_by(Product.product_id)).scalars().all()

@router.post("/products")
def upsert_product(p: ProductIn, db: Session = Depends(get_db)):
    return _upsert(db, Product, "product_id", p.model_dump())

@router.get("/shift-rotation")
def shift_rotation(db: Session = Depends(get_db)):
    rows = db.execute(select(ShiftRotation).order_by(ShiftRotation.team_id)).scalars().all()
    return [{
        "team_id": r.team_id,
        "team_name": r.team_name,
        "anchor_sunday": r.anchor_monday + timedelta(days=6),
        "anchor_shift": r.anchor_shift,
        "rotation_pattern": r.rotation_pattern,
        "active": r.active,
    } for r in rows]

@router.post("/shift-rotation")
def upsert_shift_rotation(p: ShiftRotationIn, db: Session = Depends(get_db)):
    data = p.model_dump(exclude={"anchor_sunday"})
    data["anchor_monday"] = p.anchor_sunday - timedelta(days=6)
    return _upsert(db, ShiftRotation, "team_id", data)

@router.get("/shift-rotation/resolve")
def resolve_team_shift(team_id: str, operating_date: date, db: Session = Depends(get_db)):
    row = db.get(ShiftRotation, team_id)
    if not row or not row.active:
        raise HTTPException(404, "Rotation team not found or inactive")
    try:
        shift = resolve_rotation_shift(row, operating_date)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"team_id": team_id, "operating_date": operating_date, "shift": shift}

@router.get("/person-shift/{employee_id}")
def person_shift(employee_id: str, operating_date: date, db: Session = Depends(get_db)):
    person = db.get(Person, employee_id)
    if not person or not person.active:
        raise HTTPException(404, "Person not found or inactive")
    team = (person.rotation_team or "").strip().upper()
    if team == "GENERAL":
        return {"employee_id": employee_id, "operating_date": operating_date, "rotation_team": team, "shift": "GENERAL"}
    if not team:
        raise HTTPException(422, "Person has no RotationTeam")
    row = db.get(ShiftRotation, team)
    if not row or not row.active:
        raise HTTPException(422, f"Rotation team {team} is missing or inactive")
    return {"employee_id": employee_id, "operating_date": operating_date, "rotation_team": team,
            "shift": resolve_rotation_shift(row, operating_date)}

@router.get("/shifts")
def shifts(db: Session = Depends(get_db)):
    return db.execute(select(ShiftMaster).order_by(ShiftMaster.shift)).scalars().all()

@router.post("/shifts")
def upsert_shift(p: ShiftMasterIn, db: Session = Depends(get_db)):
    return _upsert(db, ShiftMaster, "shift", p.model_dump())

@router.get("/activities")
def activities(db: Session = Depends(get_db)):
    return db.execute(select(ActivityMaster).order_by(ActivityMaster.activity)).scalars().all()

@router.post("/activities")
def upsert_activity(p: ActivityIn, db: Session = Depends(get_db)):
    return _upsert(db, ActivityMaster, "activity", p.model_dump())

@router.get("/hsd-tankers")
def hsd_tankers(db: Session = Depends(get_db)):
    return db.execute(select(HsdTanker).order_by(HsdTanker.tanker_id)).scalars().all()

@router.post("/hsd-tankers")
def upsert_hsd_tanker(p: HsdTankerIn, db: Session = Depends(get_db)):
    return _upsert(db, HsdTanker, "tanker_id", p.model_dump())

@router.get("/vehicle-aliases")
def vehicle_aliases(db: Session = Depends(get_db)):
    return db.execute(select(VehicleAlias).order_by(VehicleAlias.alias)).scalars().all()

@router.post("/vehicle-aliases")
def upsert_vehicle_alias(p: VehicleAliasIn, db: Session = Depends(get_db)):
    return _upsert(db, VehicleAlias, "alias", p.model_dump())

@router.get("/location-aliases")
def location_aliases(db: Session = Depends(get_db)):
    return db.execute(select(LocationAlias).order_by(LocationAlias.alias)).scalars().all()

@router.post("/location-aliases")
def upsert_location_alias(p: LocationAliasIn, db: Session = Depends(get_db)):
    return _upsert(db, LocationAlias, "alias", p.model_dump())

@router.get("/material-aliases")
def material_aliases(db: Session = Depends(get_db)):
    return db.execute(select(MaterialAlias).order_by(MaterialAlias.alias)).scalars().all()

@router.post("/material-aliases")
def upsert_material_alias(p: MaterialAliasIn, db: Session = Depends(get_db)):
    return _upsert(db, MaterialAlias, "alias", p.model_dump())
