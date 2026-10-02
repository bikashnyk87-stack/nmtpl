from __future__ import annotations
from datetime import date, datetime, time
from decimal import Decimal
from pydantic import BaseModel, Field

class HealthOut(BaseModel):
    ok: bool
    app: str
    database: str

class PersonIn(BaseModel):
    employee_id: str
    name: str
    role: str
    department: str | None = None
    mobile: str | None = None
    rotation_team: str | None = None
    active: bool = True

class EquipmentIn(BaseModel):
    machine_id: str
    type: str
    group: str
    door_no: str | None = None
    vehicle_no: str | None = None
    make_model: str | None = None
    bucket_cum: float | None = None
    rated_payload_t: float | None = None
    rated_output_tph: float | None = None
    standing_tare_kg: float | None = None
    ownership: str | None = None
    active: bool = True

class LocationIn(BaseModel):
    location_id: str
    location_name: str
    location_type: str | None = None
    active: bool = True


class ProductIn(BaseModel):
    product_id: str
    name: str
    size_spec: str | None = None
    target_fe_pct: float | None = None
    bulk_density: float | None = None
    saleable: bool = False
    wb_material_codes: str | None = None
    active: bool = True

class ShiftRotationIn(BaseModel):
    team_id: str
    team_name: str
    anchor_sunday: date
    anchor_shift: str
    rotation_pattern: str = "A,C,B"
    active: bool = True

class ShiftMasterIn(BaseModel):
    shift: str
    start_time: time
    end_time: time
    scheduled_hours: float = Field(gt=0, le=24)
    active: bool = True

class ActivityIn(BaseModel):
    activity: str
    vehicle_required: bool = False
    active: bool = True

class HsdTankerIn(BaseModel):
    tanker_id: str
    vehicle_no: str | None = None
    capacity_l: Decimal = Field(gt=0)
    active: bool = True

class VehicleAliasIn(BaseModel):
    alias: str
    machine_id: str
    active: bool = True

class LocationAliasIn(BaseModel):
    alias: str
    location_id: str
    direction: str = "ANY"
    active: bool = True

class MaterialAliasIn(BaseModel):
    alias: str
    product_id: str
    active: bool = True

class TripStartIn(BaseModel):
    source_location_id: str
    destination_location_id: str | None = None
    activity: str = "LOADING"
    machine_id: str
    vehicle_id: str | None = None
    material_id: str | None = None
    request_id: str
    actor: str = "admin"

class HsdReceiptIn(BaseModel):
    tanker_id: str
    litres: Decimal = Field(gt=0)
    rate_per_l: Decimal = Field(gt=0)
    supplier: str
    invoice_no: str | None = None
    pump_location: str | None = None
    request_id: str

class HsdIssueIn(BaseModel):
    tanker_id: str
    machine_id: str
    litres: Decimal = Field(gt=0)
    request_id: str
    location_id: str | None = None
    meter_type: str | None = None
    meter_reading: Decimal | None = None
    recipient_employee_id: str | None = None
    reference: str | None = None

class PersonAttendanceIn(BaseModel):
    operating_date: date
    shift: str
    employee_id: str
    attendance: str = "PRESENT"
    in_at: datetime | None = None
    out_at: datetime | None = None
    out_source: str | None = None
    review_status: str | None = None
    remarks: str | None = None
    entered_by: str = "admin"

class EquipmentAttendanceIn(BaseModel):
    operating_date: date
    shift: str
    machine_id: str
    attendance: str = "PRESENT"
    condition: str | None = "WORKING"
    meter_type: str | None = None
    opening_meter: Decimal | None = None
    closing_meter: Decimal | None = None
    remarks: str | None = None
    entered_by: str = "admin"

class ShiftCrewAssignIn(BaseModel):
    operating_date: date
    shift: str
    employee_id: str
    machine_id: str
    from_at: datetime | None = None
    reason: str = "Shift crew assignment"
    changed_by: str = "admin"

class ShiftDeploymentAssignIn(BaseModel):
    operating_date: date
    shift: str
    machine_id: str
    location_id: str
    from_at: datetime | None = None
    reason: str = "Shift deployment change"
    changed_by: str = "admin"

class ShiftStateIn(BaseModel):
    operating_date: date
    shift: str
    status: str
    reason: str | None = None
    changed_by: str = "admin"
