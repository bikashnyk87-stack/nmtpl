from __future__ import annotations
from datetime import date, datetime, time
from decimal import Decimal
from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, Time, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Person(Base):
    __tablename__ = "persons"
    employee_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False)
    department: Mapped[str | None] = mapped_column(String(80))
    mobile: Mapped[str | None] = mapped_column(String(30))
    rotation_team: Mapped[str | None] = mapped_column(String(30), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

class Equipment(Base):
    __tablename__ = "equipment"
    machine_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    door_no: Mapped[str | None] = mapped_column(String(50))
    vehicle_no: Mapped[str | None] = mapped_column(String(50), index=True)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    group: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    make_model: Mapped[str | None] = mapped_column(String(120))
    bucket_cum: Mapped[float | None] = mapped_column(Float)
    rated_payload_t: Mapped[float | None] = mapped_column(Float)
    rated_output_tph: Mapped[float | None] = mapped_column(Float)
    standing_tare_kg: Mapped[float | None] = mapped_column(Float)
    ownership: Mapped[str | None] = mapped_column(String(30), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

class Location(Base):
    __tablename__ = "locations"
    location_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    location_name: Mapped[str] = mapped_column(String(160), nullable=False)
    location_type: Mapped[str | None] = mapped_column(String(60))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

class Product(Base):
    __tablename__ = "products"
    product_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    size_spec: Mapped[str | None] = mapped_column(String(120))
    target_fe_pct: Mapped[float | None] = mapped_column(Float)
    bulk_density: Mapped[float | None] = mapped_column(Float)
    saleable: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    wb_material_codes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

class ShiftRotation(Base):
    __tablename__ = "shift_rotation"
    team_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    team_name: Mapped[str] = mapped_column(String(80), nullable=False)
    anchor_monday: Mapped[date] = mapped_column(Date, nullable=False)
    anchor_shift: Mapped[str] = mapped_column(String(10), nullable=False)
    rotation_pattern: Mapped[str] = mapped_column(String(40), default="A,C,B")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class ShiftMaster(Base):
    __tablename__ = "shift_master"
    shift: Mapped[str] = mapped_column(String(20), primary_key=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    scheduled_hours: Mapped[float] = mapped_column(Float, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

class ActivityMaster(Base):
    __tablename__ = "activity_master"
    activity: Mapped[str] = mapped_column(String(60), primary_key=True)
    vehicle_required: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

class PersonAttendance(Base):
    __tablename__ = "person_attendance"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(10), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("persons.employee_id"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worked_hours: Mapped[Decimal | None] = mapped_column(Numeric(8,2))
    out_source: Mapped[str | None] = mapped_column(String(40))
    review_status: Mapped[str | None] = mapped_column(String(20))
    remarks: Mapped[str | None] = mapped_column(String(250))
    entered_by: Mapped[str | None] = mapped_column(String(60))
    entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("operating_date","shift","employee_id", name="uq_person_att_shift"),)

class EquipmentAttendance(Base):
    __tablename__ = "equipment_attendance"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(10), index=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    condition: Mapped[str | None] = mapped_column(String(30), index=True)
    meter_type: Mapped[str | None] = mapped_column(String(10))
    opening_meter: Mapped[Decimal | None] = mapped_column(Numeric(14,2))
    closing_meter: Mapped[Decimal | None] = mapped_column(Numeric(14,2))
    run_meter: Mapped[Decimal | None] = mapped_column(Numeric(14,2))
    remarks: Mapped[str | None] = mapped_column(String(250))
    entered_by: Mapped[str | None] = mapped_column(String(60))
    entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("operating_date","shift","machine_id", name="uq_equipment_att_shift"),)

class ShiftCrew(Base):
    __tablename__ = "shift_crew"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(10), index=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("persons.employee_id"), index=True)
    from_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    to_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    reason: Mapped[str | None] = mapped_column(String(250))
    changed_by: Mapped[str | None] = mapped_column(String(60))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_shift_crew_active_machine", "operating_date","shift","machine_id","status"),
        Index("ix_shift_crew_active_person", "operating_date","shift","employee_id","status"),
    )

class ShiftDeployment(Base):
    __tablename__ = "shift_deployment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(10), index=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.location_id"), index=True)
    from_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    to_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    reason: Mapped[str | None] = mapped_column(String(250))
    changed_by: Mapped[str | None] = mapped_column(String(60))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class ShiftState(Base):
    __tablename__ = "shift_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    reason: Mapped[str | None] = mapped_column(String(250))
    changed_by: Mapped[str | None] = mapped_column(String(60))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("operating_date", "shift", name="uq_shift_state_date_shift"),)

class LoadTrip(Base):
    __tablename__ = "load_trip"
    trip_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(10), index=True)
    source_location_id: Mapped[str] = mapped_column(ForeignKey("locations.location_id"), index=True)
    destination_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.location_id"), index=True)
    activity: Mapped[str] = mapped_column(String(40), index=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    machine_operator_id: Mapped[str | None] = mapped_column(ForeignKey("persons.employee_id"))
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    vehicle_driver_id: Mapped[str | None] = mapped_column(ForeignKey("persons.employee_id"))
    trip_seq: Mapped[int | None] = mapped_column(Integer)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("products.product_id"), index=True)
    loading_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    loading_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    unload_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="LOADING", index=True)
    request_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_by: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        Index("ix_trip_match_queue", "operating_date","shift","vehicle_id","loading_end_at"),
    )

class WbImportBatch(Base):
    __tablename__ = "wb_import_batch"
    batch_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(10), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    review_rows: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class WbMovement(Base):
    __tablename__ = "wb_movement"
    movement_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("wb_import_batch.batch_id"), index=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(10), index=True)
    movement_no: Mapped[str] = mapped_column(String(60))
    vehicle_raw: Mapped[str] = mapped_column(String(80), index=True)
    vehicle_id: Mapped[str | None] = mapped_column(String(50), index=True)
    material_code: Mapped[str | None] = mapped_column(String(60), index=True)
    material_name: Mapped[str | None] = mapped_column(String(120))
    source_raw: Mapped[str | None] = mapped_column(String(160))
    destination_raw: Mapped[str | None] = mapped_column(String(160))
    tare_kg: Mapped[Decimal] = mapped_column(Numeric(14,2))
    gross_kg: Mapped[Decimal] = mapped_column(Numeric(14,2))
    net_kg: Mapped[Decimal] = mapped_column(Numeric(14,2))
    weigh_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    row_status: Mapped[str] = mapped_column(String(20), index=True)
    issue: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        Index("ix_wb_match_queue", "operating_date","shift","vehicle_id","weigh_at"),
    )

class LoadWbMatch(Base):
    __tablename__ = "load_wb_match"
    match_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("load_trip.trip_id"), unique=True, index=True)
    movement_key: Mapped[str] = mapped_column(ForeignKey("wb_movement.movement_key"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    method: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class WbHeaderAlias(Base):
    __tablename__ = "wb_header_alias"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_field: Mapped[str] = mapped_column(String(40), index=True)
    header_alias: Mapped[str] = mapped_column(String(120))
    occurrence: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    __table_args__ = (
        UniqueConstraint("canonical_field", "header_alias", "occurrence", name="uq_wb_header_alias"),
    )

class VehicleAlias(Base):
    __tablename__ = "vehicle_alias"
    alias: Mapped[str] = mapped_column(String(80), primary_key=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class LocationAlias(Base):
    __tablename__ = "location_alias"
    alias: Mapped[str] = mapped_column(String(180), primary_key=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.location_id"), index=True)
    direction: Mapped[str] = mapped_column(String(20), default="ANY")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class MaterialAlias(Base):
    __tablename__ = "material_alias"
    alias: Mapped[str] = mapped_column(String(120), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class HsdTanker(Base):
    __tablename__ = "hsd_tanker"
    tanker_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    vehicle_no: Mapped[str | None] = mapped_column(String(50))
    capacity_l: Mapped[Decimal] = mapped_column(Numeric(14,2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class HsdPurchaseLot(Base):
    __tablename__ = "hsd_purchase_lot"
    lot_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tanker_id: Mapped[str] = mapped_column(ForeignKey("hsd_tanker.tanker_id"), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    supplier: Mapped[str] = mapped_column(String(120))
    invoice_no: Mapped[str | None] = mapped_column(String(80))
    pump_location: Mapped[str | None] = mapped_column(String(120))
    litres_received: Mapped[Decimal] = mapped_column(Numeric(14,2))
    litres_remaining: Mapped[Decimal] = mapped_column(Numeric(14,2), index=True)
    rate_per_l: Mapped[Decimal] = mapped_column(Numeric(12,4))
    amount: Mapped[Decimal] = mapped_column(Numeric(16,2))
    request_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)

class HsdIssue(Base):
    __tablename__ = "hsd_issue"
    issue_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(10), index=True)
    tanker_id: Mapped[str] = mapped_column(ForeignKey("hsd_tanker.tanker_id"), index=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    litres: Mapped[Decimal] = mapped_column(Numeric(14,2))
    amount: Mapped[Decimal] = mapped_column(Numeric(16,2))
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.location_id"))
    meter_type: Mapped[str | None] = mapped_column(String(10))
    meter_reading: Mapped[Decimal | None] = mapped_column(Numeric(14,2))
    recipient_employee_id: Mapped[str | None] = mapped_column(ForeignKey("persons.employee_id"))
    reference: Mapped[str | None] = mapped_column(String(100))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    request_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)

class HsdIssueAllocation(Base):
    __tablename__ = "hsd_issue_allocation"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("hsd_issue.issue_id"), index=True)
    lot_id: Mapped[str] = mapped_column(ForeignKey("hsd_purchase_lot.lot_id"), index=True)
    litres: Mapped[Decimal] = mapped_column(Numeric(14,2))
    rate_per_l: Mapped[Decimal] = mapped_column(Numeric(12,4))
    amount: Mapped[Decimal] = mapped_column(Numeric(16,2))

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(120))
    detail: Mapped[str | None] = mapped_column(Text)


class MasterOption(Base):
    __tablename__ = "master_options"
    category: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(80), primary_key=True)
