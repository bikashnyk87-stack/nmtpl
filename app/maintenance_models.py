from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class MaintenanceBreakdown(Base):
    __tablename__ = "maintenance_breakdown"

    breakdown_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str | None] = mapped_column(String(20), index=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    problem_category: Mapped[str] = mapped_column(String(80), index=True)
    problem: Mapped[str] = mapped_column(String(300))
    location_id: Mapped[str | None] = mapped_column(String(80), index=True)
    meter_type: Mapped[str | None] = mapped_column(String(20))
    meter_reading: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    status: Mapped[str] = mapped_column(String(30), default="OPEN", index=True)
    job_card_id: Mapped[str | None] = mapped_column(String(70), index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    downtime_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    reported_by: Mapped[str] = mapped_column(String(60))
    released_by: Mapped[str | None] = mapped_column(String(60))
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        Index("ix_maint_bd_open_asset", "site_id", "asset_id", "status"),
        Index("ix_maint_bd_period", "site_id", "operating_date", "status"),
    )


class MaintenanceJobCard(Base):
    __tablename__ = "maintenance_job_card"

    job_card_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    source_type: Mapped[str] = mapped_column(String(30), default="GENERAL", index=True)
    source_id: Mapped[str | None] = mapped_column(String(70), index=True)
    job_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), default="OPEN", index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meter_type: Mapped[str | None] = mapped_column(String(20))
    meter_reading: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    complaint: Mapped[str | None] = mapped_column(Text)
    diagnosis: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    action_taken: Mapped[str | None] = mapped_column(Text)
    mechanic_id: Mapped[str | None] = mapped_column(ForeignKey("persons.employee_id"), index=True)
    labour_hours: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    external_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    remarks: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        Index("ix_maint_job_active", "site_id", "asset_id", "status"),
        Index("ix_maint_job_period", "site_id", "opened_at", "job_type"),
    )


class MaintenanceServicePlan(Base):
    __tablename__ = "maintenance_service_plan"

    plan_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    equipment_type: Mapped[str | None] = mapped_column(String(60), index=True)
    make_model: Mapped[str | None] = mapped_column(String(120), index=True)
    service_name: Mapped[str] = mapped_column(String(120), index=True)
    schedule_basis: Mapped[str] = mapped_column(String(30), index=True)
    interval_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    calendar_interval_days: Mapped[int | None] = mapped_column(Integer)
    warning_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    last_service_at: Mapped[date | None] = mapped_column(Date)
    last_meter: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    next_due_at: Mapped[date | None] = mapped_column(Date, index=True)
    next_due_meter: Mapped[Decimal | None] = mapped_column(Numeric(16, 3), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    entered_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class MaintenanceServiceHistory(Base):
    __tablename__ = "maintenance_service_history"

    service_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey("maintenance_service_plan.plan_id"), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    job_card_id: Mapped[str | None] = mapped_column(ForeignKey("maintenance_job_card.job_card_id"), index=True)
    serviced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    meter_type: Mapped[str | None] = mapped_column(String(20))
    meter_reading: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    next_due_at: Mapped[date | None] = mapped_column(Date)
    next_due_meter: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    remarks: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class MaintenanceComponentMaster(Base):
    __tablename__ = "maintenance_component_master"

    component_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    component_name: Mapped[str] = mapped_column(String(140), index=True)
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    part_number: Mapped[str | None] = mapped_column(String(100), index=True)
    unit: Mapped[str] = mapped_column(String(30), default="NOS")
    store_item_id: Mapped[str | None] = mapped_column(String(80), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    entered_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("component_name", "part_number", name="uq_maint_component_name_part"),)


class EquipmentComponentSchedule(Base):
    __tablename__ = "equipment_component_schedule"

    schedule_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    equipment_type: Mapped[str | None] = mapped_column(String(60), index=True)
    make_model: Mapped[str | None] = mapped_column(String(120), index=True)
    component_id: Mapped[str] = mapped_column(ForeignKey("maintenance_component_master.component_id"), index=True)
    schedule_basis: Mapped[str] = mapped_column(String(30), index=True)
    interval_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    calendar_interval_days: Mapped[int | None] = mapped_column(Integer)
    warning_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    required_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("1"))
    last_changed_at: Mapped[date | None] = mapped_column(Date)
    last_meter: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    next_due_at: Mapped[date | None] = mapped_column(Date, index=True)
    next_due_meter: Mapped[Decimal | None] = mapped_column(Numeric(16, 3), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    entered_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ComponentChangeHistory(Base):
    __tablename__ = "component_change_history"

    change_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    schedule_id: Mapped[str] = mapped_column(ForeignKey("equipment_component_schedule.schedule_id"), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    job_card_id: Mapped[str | None] = mapped_column(ForeignKey("maintenance_job_card.job_card_id"), index=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    meter_type: Mapped[str | None] = mapped_column(String(20))
    meter_reading: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("1"))
    remarks: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class MaintenancePmPlan(Base):
    __tablename__ = "maintenance_pm_plan"

    pm_plan_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    equipment_type: Mapped[str | None] = mapped_column(String(60), index=True)
    activity: Mapped[str] = mapped_column(String(40), index=True)
    plan_name: Mapped[str] = mapped_column(String(120))
    schedule_basis: Mapped[str] = mapped_column(String(30), index=True)
    interval_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    calendar_interval_days: Mapped[int | None] = mapped_column(Integer)
    warning_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    last_done_at: Mapped[date | None] = mapped_column(Date)
    last_meter: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    next_due_at: Mapped[date | None] = mapped_column(Date, index=True)
    next_due_meter: Mapped[Decimal | None] = mapped_column(Numeric(16, 3), index=True)
    checklist_json: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    entered_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class MaintenancePmExecution(Base):
    __tablename__ = "maintenance_pm_execution"

    execution_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    pm_plan_id: Mapped[str | None] = mapped_column(ForeignKey("maintenance_pm_plan.pm_plan_id"), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    activity: Mapped[str] = mapped_column(String(40), index=True)
    job_card_id: Mapped[str | None] = mapped_column(ForeignKey("maintenance_job_card.job_card_id"), index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    meter_type: Mapped[str | None] = mapped_column(String(20))
    meter_reading: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    result: Mapped[str] = mapped_column(String(30), default="COMPLETE", index=True)
    checklist_json: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class MaintenanceDefProfile(Base):
    __tablename__ = "maintenance_def_profile"

    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), primary_key=True)
    tank_capacity_l: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    normal_issue_qty_l: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    minimum_level_l: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    expected_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    rate_basis: Mapped[str | None] = mapped_column(String(30))  # PER_HOUR/PER_KM/PCT_HSD
    alert_level_l: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_by: Mapped[str] = mapped_column(String(60))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class MaintenanceDefTransaction(Base):
    __tablename__ = "maintenance_def_transaction"

    def_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str | None] = mapped_column(String(20), index=True)
    quantity_l: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    meter_type: Mapped[str | None] = mapped_column(String(20))
    meter_reading: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    operator_id: Mapped[str | None] = mapped_column(ForeignKey("persons.employee_id"), index=True)
    issue_reference: Mapped[str | None] = mapped_column(String(120), index=True)
    remarks: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (Index("ix_maint_def_period", "site_id", "operating_date", "asset_id"),)


class MaintenanceLubricantUsage(Base):
    __tablename__ = "maintenance_lubricant_usage"

    usage_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    job_card_id: Mapped[str | None] = mapped_column(ForeignKey("maintenance_job_card.job_card_id"), index=True)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lubricant_type: Mapped[str] = mapped_column(String(80), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(String(20), default="L")
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    remarks: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[str] = mapped_column(String(60))


class MaintenanceSpareUsage(Base):
    __tablename__ = "maintenance_spare_usage"

    usage_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    job_card_id: Mapped[str | None] = mapped_column(ForeignKey("maintenance_job_card.job_card_id"), index=True)
    component_id: Mapped[str | None] = mapped_column(ForeignKey("maintenance_component_master.component_id"), index=True)
    store_item_id: Mapped[str | None] = mapped_column(String(80), index=True)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    description: Mapped[str] = mapped_column(String(180))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(String(30), default="NOS")
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    store_issue_reference: Mapped[str | None] = mapped_column(String(100), index=True)
    remarks: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[str] = mapped_column(String(60))


class MaintenanceTyre(Base):
    __tablename__ = "maintenance_tyre"

    tyre_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    serial_no: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    brand: Mapped[str | None] = mapped_column(String(80), index=True)
    tyre_size: Mapped[str | None] = mapped_column(String(60))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(30), default="STORE", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    entered_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class MaintenanceTyreFitment(Base):
    __tablename__ = "maintenance_tyre_fitment"

    fitment_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    tyre_id: Mapped[str] = mapped_column(ForeignKey("maintenance_tyre.tyre_id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    axle: Mapped[str | None] = mapped_column(String(40))
    position: Mapped[str | None] = mapped_column(String(60))
    fitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fit_kmr: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    removal_kmr: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    running_km: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    removal_reason: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(30), default="FITTED", index=True)
    entered_by: Mapped[str] = mapped_column(String(60))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class EquipmentDocument(Base):
    __tablename__ = "maintenance_equipment_document"

    document_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    document_type: Mapped[str] = mapped_column(String(50), index=True)
    reference_no: Mapped[str | None] = mapped_column(String(120))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, index=True)
    remarks: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    entered_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


MAINTENANCE_TABLES = [
    MaintenanceBreakdown,
    MaintenanceJobCard,
    MaintenanceServicePlan,
    MaintenanceServiceHistory,
    MaintenanceComponentMaster,
    EquipmentComponentSchedule,
    ComponentChangeHistory,
    MaintenancePmPlan,
    MaintenancePmExecution,
    MaintenanceDefProfile,
    MaintenanceDefTransaction,
    MaintenanceLubricantUsage,
    MaintenanceSpareUsage,
    MaintenanceTyre,
    MaintenanceTyreFitment,
    EquipmentDocument,
]


def create_maintenance_tables(engine) -> None:
    """Additive Mechanical Maintenance tables only; existing TIOM tables are untouched."""
    for model in MAINTENANCE_TABLES:
        model.__table__.create(engine, checkfirst=True)
