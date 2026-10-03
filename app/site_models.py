from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Site(Base):
    """Top-level tenant/site definition.

    Existing v0.8 operational tables remain logically TIOM. New multi-site
    modules reference this table explicitly.
    """

    __tablename__ = "site"

    site_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    site_name: Mapped[str] = mapped_column(String(120), nullable=False)
    short_name: Mapped[str] = mapped_column(String(40), nullable=False)
    timezone: Mapped[str] = mapped_column(String(60), default="Asia/Kolkata")
    map_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class SiteShift(Base):
    __tablename__ = "site_shift"

    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), primary_key=True)
    shift: Mapped[str] = mapped_column(String(20), primary_key=True)
    shift_name: Mapped[str | None] = mapped_column(String(60))
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    scheduled_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class UserSiteAccess(Base):
    __tablename__ = "user_site_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login_id: Mapped[str] = mapped_column(ForeignKey("web_user.login_id"), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    default_site: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    assigned_by: Mapped[str | None] = mapped_column(String(60))
    __table_args__ = (UniqueConstraint("login_id", "site_id", name="uq_user_site_access"),)


class UserPermission(Base):
    """Fine-grained permission grants.

    permission examples:
      CENTRAL.DASHBOARD.VIEW
      SOCP.TRIP.CREATE
      SOCP.WB.APPROVE
      KOCP.MCL_FACTOR.APPROVE

    Site/module/action remain separate columns so permission checks can be
    indexed and reported even though a canonical permission string is stored.
    """

    __tablename__ = "user_permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login_id: Mapped[str] = mapped_column(ForeignKey("web_user.login_id"), index=True)
    site_id: Mapped[str] = mapped_column(String(20), index=True)
    module: Mapped[str] = mapped_column(String(40), index=True)
    action: Mapped[str] = mapped_column(String(30), index=True)
    permission: Mapped[str] = mapped_column(String(120), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    assigned_by: Mapped[str | None] = mapped_column(String(60))
    __table_args__ = (
        UniqueConstraint("login_id", "permission", name="uq_user_permission"),
        Index("ix_user_permission_lookup", "login_id", "site_id", "module", "action", "active"),
    )


class PersonSiteAssignment(Base):
    __tablename__ = "person_site_assignment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("persons.employee_id"), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, index=True)
    primary_site: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    source: Mapped[str] = mapped_column(String(40), default="MASTER")
    import_batch_id: Mapped[str | None] = mapped_column(String(60), index=True)
    __table_args__ = (
        Index("ix_person_site_effective", "employee_id", "site_id", "effective_from", "effective_to"),
    )


class EquipmentSiteAssignment(Base):
    __tablename__ = "equipment_site_assignment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, index=True)
    ownership: Mapped[str | None] = mapped_column(String(40), index=True)
    party: Mapped[str | None] = mapped_column(String(120), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    source: Mapped[str] = mapped_column(String(40), default="MASTER")
    import_batch_id: Mapped[str | None] = mapped_column(String(60), index=True)
    __table_args__ = (
        Index("ix_equipment_site_effective", "machine_id", "site_id", "effective_from", "effective_to"),
    )


class SiteLocation(Base):
    __tablename__ = "site_location"

    site_location_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    code: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    location_type: Mapped[str | None] = mapped_column(String(60), index=True)
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    import_batch_id: Mapped[str | None] = mapped_column(String(60), index=True)
    __table_args__ = (UniqueConstraint("site_id", "code", name="uq_site_location_code"),)


class SiteMaterial(Base):
    __tablename__ = "site_material"

    site_material_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    code: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    material_group: Mapped[str | None] = mapped_column(String(60), index=True)
    default_unit: Mapped[str] = mapped_column(String(20), default="MT")
    billable_unit: Mapped[str | None] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    __table_args__ = (UniqueConstraint("site_id", "code", name="uq_site_material_code"),)


class MasterImportBatch(Base):
    __tablename__ = "master_import_batch"

    batch_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    master_type: Mapped[str] = mapped_column(String(40), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    update_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str] = mapped_column(String(60))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    confirmed_by: Mapped[str | None] = mapped_column(String(60))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class MasterImportRow(Base):
    __tablename__ = "master_import_row"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("master_import_batch.batch_id"), index=True)
    row_no: Mapped[int] = mapped_column(Integer)
    row_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="VALID", index=True)
    error_text: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("batch_id", "row_no", name="uq_master_import_row"),)


class SiteTrip(Base):
    """Common trip engine for SOCP/KOCP and future migrated site operations."""

    __tablename__ = "site_trip"

    trip_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(20), index=True)
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    vehicle_raw: Mapped[str | None] = mapped_column(String(80), index=True)
    driver_id: Mapped[str | None] = mapped_column(ForeignKey("persons.employee_id"), index=True)
    loading_equipment_id: Mapped[str | None] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    loading_operator_id: Mapped[str | None] = mapped_column(ForeignKey("persons.employee_id"), index=True)
    source_location_id: Mapped[str | None] = mapped_column(ForeignKey("site_location.site_location_id"), index=True)
    destination_location_id: Mapped[str | None] = mapped_column(ForeignKey("site_location.site_location_id"), index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("site_material.site_material_id"), index=True)
    gp_no: Mapped[str | None] = mapped_column(String(80), index=True)
    trip_seq: Mapped[int | None] = mapped_column(Integer)
    loading_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    loading_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unloading_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unloading_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quantity_mt: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    quantity_cum: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    weight_basis: Mapped[str | None] = mapped_column(String(40), index=True)
    factor_id: Mapped[str | None] = mapped_column(String(60), index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="PORTAL", index=True)
    source_record_uid: Mapped[str | None] = mapped_column(String(120), index=True)
    source_batch_id: Mapped[str | None] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(30), default="POSTED", index=True)
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        Index("ix_site_trip_dashboard", "site_id", "operating_date", "shift", "status"),
        Index("ix_site_trip_vehicle_time", "site_id", "vehicle_id", "event_at"),
        UniqueConstraint("site_id", "source_type", "source_record_uid", name="uq_site_trip_source_uid"),
    )



class SiteOperationalImportBatch(Base):
    __tablename__ = "site_operational_import_batch"

    batch_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    import_type: Mapped[str] = mapped_column(String(40), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), default="PREVIEW", index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str] = mapped_column(String(60))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    confirmed_by: Mapped[str | None] = mapped_column(String(60))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SiteOperationalImportRow(Base):
    __tablename__ = "site_operational_import_row"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("site_operational_import_batch.batch_id"), index=True)
    row_no: Mapped[int] = mapped_column(Integer)
    row_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="VALID", index=True)
    error_text: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("batch_id", "row_no", name="uq_site_operational_import_row"),)

class SiteWbImportBatch(Base):
    __tablename__ = "site_wb_import_batch"

    batch_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="WB_MIS", index=True)
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), default="STAGED", index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    review_rows: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str] = mapped_column(String(60))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    confirmed_by: Mapped[str | None] = mapped_column(String(60))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SiteWbMovement(Base):
    __tablename__ = "site_wb_movement"

    movement_key: Mapped[str] = mapped_column(String(140), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("site_wb_import_batch.batch_id"), index=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(20), index=True)
    wb_id: Mapped[str] = mapped_column(String(80), index=True)
    weigh_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    vehicle_raw: Mapped[str] = mapped_column(String(80), index=True)
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    party: Mapped[str | None] = mapped_column(String(120), index=True)
    source_raw: Mapped[str | None] = mapped_column(String(160))
    destination_raw: Mapped[str | None] = mapped_column(String(160))
    gross_kg: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    tare_kg: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    net_kg: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    row_status: Mapped[str] = mapped_column(String(30), default="VALID", index=True)
    issue: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("site_id", "wb_id", name="uq_site_wb_id"),
        Index("ix_site_wb_dashboard", "site_id", "operating_date", "shift", "row_status"),
    )


class SiteWeightFactor(Base):
    """MCL/site-controlled factors for operational and billing quantities.

    factor_type examples:
      COAL_AVG_MT_PER_TRIP
      OB_CUM_PER_TRIP
      OB_SURVEY_CUM
    """

    __tablename__ = "site_weight_factor"

    factor_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    factor_type: Mapped[str] = mapped_column(String(50), index=True)
    operating_date: Mapped[date | None] = mapped_column(Date, index=True)
    shift: Mapped[str | None] = mapped_column(String(20), index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("site_material.site_material_id"), index=True)
    vehicle_class: Mapped[str | None] = mapped_column(String(80), index=True)
    factor_value: Mapped[Decimal] = mapped_column(Numeric(16, 6))
    factor_unit: Mapped[str] = mapped_column(String(30))
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, index=True)
    source_org: Mapped[str] = mapped_column(String(80), default="MCL")
    reference_no: Mapped[str | None] = mapped_column(String(120))
    reference_date: Mapped[date | None] = mapped_column(Date)
    document_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    approved_by: Mapped[str | None] = mapped_column(String(60))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        Index("ix_site_factor_lookup", "site_id", "factor_type", "effective_from", "effective_to", "status"),
    )


class SiteHsdTransaction(Base):
    __tablename__ = "site_hsd_transaction"

    transaction_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str | None] = mapped_column(String(20), index=True)
    transaction_type: Mapped[str] = mapped_column(String(30), index=True)  # OPENING/RECEIPT/ISSUE/ADJUSTMENT
    asset_type: Mapped[str | None] = mapped_column(String(40), index=True)
    asset_id: Mapped[str | None] = mapped_column(String(80), index=True)
    litres: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    supplier: Mapped[str | None] = mapped_column(String(120))
    reference_no: Mapped[str | None] = mapped_column(String(120))
    meter_reading: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="PORTAL")
    source_record_uid: Mapped[str | None] = mapped_column(String(120), index=True)
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(30), default="POSTED", index=True)
    __table_args__ = (
        UniqueConstraint("site_id", "source_type", "source_record_uid", name="uq_site_hsd_source_uid"),
        Index("ix_site_hsd_summary", "site_id", "operating_date", "shift", "transaction_type"),
    )


class SiteAuditLog(Base):
    __tablename__ = "site_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str | None] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(140))
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)


class SitePersonAttendance(Base):
    __tablename__ = "site_person_attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(20), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("persons.employee_id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="PRESENT", index=True)
    in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worked_hours: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    source_type: Mapped[str] = mapped_column(String(40), default="PORTAL", index=True)
    source_record_uid: Mapped[str | None] = mapped_column(String(120), index=True)
    remarks: Mapped[str | None] = mapped_column(String(300))
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("site_id", "operating_date", "shift", "employee_id", name="uq_site_person_attendance"),
        UniqueConstraint("site_id", "source_type", "source_record_uid", name="uq_site_att_source_uid"),
        Index("ix_site_attendance_dashboard", "site_id", "operating_date", "shift", "status"),
    )


class SiteAssetAttendance(Base):
    __tablename__ = "site_asset_attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(20), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING", index=True)
    condition: Mapped[str | None] = mapped_column(String(40), index=True)
    remarks: Mapped[str | None] = mapped_column(String(300))
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("site_id", "operating_date", "shift", "asset_id", name="uq_site_asset_attendance"),
        Index("ix_site_asset_att_dashboard", "site_id", "operating_date", "shift", "status"),
    )


class SiteDeployment(Base):
    __tablename__ = "site_deployment"

    deployment_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(20), index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("persons.employee_id"), index=True)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("site_location.site_location_id"), index=True)
    activity: Mapped[str | None] = mapped_column(String(80), index=True)
    from_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", index=True)
    remarks: Mapped[str | None] = mapped_column(String(300))
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        Index("ix_site_deployment_lookup", "site_id", "operating_date", "shift", "status"),
        Index("ix_site_deployment_asset", "site_id", "asset_id", "operating_date", "shift"),
        Index("ix_site_deployment_person", "site_id", "employee_id", "operating_date", "shift"),
    )


class SiteAssetMeter(Base):
    __tablename__ = "site_asset_meter"

    reading_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(20), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    meter_type: Mapped[str] = mapped_column(String(20), index=True)  # HMR/KMR/OTHER
    opening_reading: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    closing_reading: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    usage: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    source_type: Mapped[str] = mapped_column(String(40), default="PORTAL")
    remarks: Mapped[str | None] = mapped_column(String(300))
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("site_id", "operating_date", "shift", "asset_id", "meter_type", name="uq_site_asset_meter"),
        Index("ix_site_meter_dashboard", "site_id", "operating_date", "shift", "meter_type"),
    )


class SiteTripReconciliation(Base):
    __tablename__ = "site_trip_reconciliation"

    reconciliation_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(20), index=True)
    trip_id: Mapped[str | None] = mapped_column(ForeignKey("site_trip.trip_id"), unique=True, index=True)
    wb_movement_key: Mapped[str | None] = mapped_column(ForeignKey("site_wb_movement.movement_key"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)  # MATCHED/TRIP_ONLY/WB_ONLY/AMBIGUOUS/CONFLICT
    method: Mapped[str] = mapped_column(String(40), default="AUTO")
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    quantity_diff_kg: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(60))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        Index("ix_site_recon_queue", "site_id", "operating_date", "shift", "status"),
    )


class SiteSurveyMeasurement(Base):
    __tablename__ = "site_survey_measurement"

    measurement_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("site_material.site_material_id"), index=True)
    measurement_type: Mapped[str] = mapped_column(String(40), default="MCL_SURVEY", index=True)
    measured_cum: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    measured_mt: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    source_org: Mapped[str] = mapped_column(String(80), default="MCL")
    reference_no: Mapped[str | None] = mapped_column(String(120))
    reference_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    approved_by: Mapped[str | None] = mapped_column(String(60))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_site_survey_period", "site_id", "period_start", "period_end", "status"),
    )


class SiteBillingReconciliation(Base):
    __tablename__ = "site_billing_reconciliation"

    billing_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("site_material.site_material_id"), index=True)
    operational_mt: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    operational_cum: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    certified_mt: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    certified_cum: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    billable_mt: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    billable_cum: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    variance_mt: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    variance_cum: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    source_measurement_id: Mapped[str | None] = mapped_column(ForeignKey("site_survey_measurement.measurement_id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    approved_by: Mapped[str | None] = mapped_column(String(60))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_site_billing_period", "site_id", "period_start", "period_end", "status"),
    )


class SiteDataQualityIssue(Base):
    __tablename__ = "site_data_quality_issue"

    issue_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    operating_date: Mapped[date | None] = mapped_column(Date, index=True)
    shift: Mapped[str | None] = mapped_column(String(20), index=True)
    issue_type: Mapped[str] = mapped_column(String(60), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="WARNING", index=True)
    entity: Mapped[str] = mapped_column(String(60), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(140), index=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    owner: Mapped[str | None] = mapped_column(String(80))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    resolved_by: Mapped[str | None] = mapped_column(String(60))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        Index("ix_site_dq_dashboard", "site_id", "status", "severity", "operating_date"),
    )


class SiteSatelliteObservation(Base):
    __tablename__ = "site_satellite_observation"

    observation_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.site_id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="SENTINEL-2", index=True)
    image_date: Mapped[date] = mapped_column(Date, index=True)
    cloud_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    image_ref: Mapped[str | None] = mapped_column(Text)
    previous_observation_id: Mapped[str | None] = mapped_column(String(60), index=True)
    change_area_ha: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    status: Mapped[str] = mapped_column(String(30), default="AVAILABLE", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(60), default="SYSTEM")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("site_id", "provider", "image_date", name="uq_site_satellite_date"),
    )


class TiomSourceDeployment(Base):
    """TIOM shift-level source ↔ loader/excavator deployment used by MIS entry.

    Kept separate from the legacy attendance/shift-control deployment table so
    Phase 1 can capture the field reality without re-enabling those workflows.
    """
    __tablename__ = "tiom_source_deployment"

    deployment_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(20), index=True)
    source_location_id: Mapped[str] = mapped_column(ForeignKey("locations.location_id"), index=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    activity: Mapped[str] = mapped_column(String(40), default="LOADING", index=True)
    from_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    to_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(String(300))
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        Index("ix_tiom_source_deploy_lookup", "operating_date", "shift", "source_location_id", "machine_id", "active"),
    )


class TiomShiftProductionReport(Base):
    """One TIOM management shift-production document per operating date/shift."""
    __tablename__ = "tiom_shift_production_report"

    report_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    remarks: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    submitted_by: Mapped[str | None] = mapped_column(String(60))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("operating_date", "shift", name="uq_tiom_shift_production_report"),)


class TiomShiftProductionMovement(Base):
    """Underlying plant/shifting movement rows used to generate the management report."""
    __tablename__ = "tiom_shift_production_movement"

    movement_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("tiom_shift_production_report.report_id"), index=True)
    row_no: Mapped[int] = mapped_column(Integer)
    movement_code: Mapped[str] = mapped_column(String(60), index=True)
    source_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.location_id"), index=True)
    destination_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.location_id"), index=True)
    trips: Mapped[int | None] = mapped_column(Integer)
    qty_mt: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=Decimal("0"))
    remarks: Mapped[str | None] = mapped_column(String(300))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("report_id", "row_no", name="uq_tiom_shift_prod_row"),)


class TiomShiftReportBaseline(Base):
    """Opening cumulative values used to replace fragile Excel carry-forward formulas."""
    __tablename__ = "tiom_shift_report_baseline"

    line_code: Mapped[str] = mapped_column(String(60), primary_key=True)
    effective_date: Mapped[date] = mapped_column(Date, primary_key=True)
    opening_qty_mt: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(String(300))
    entered_by: Mapped[str] = mapped_column(String(60), default="SYSTEM")
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TiomMisReport(Base):
    """TIOM paper driver/shift report header.

    ERP-linked driver/shift evidence. WB-linked rows inherit authoritative WB
    tonnes without adding them twice; non-WB rows (for example OB) use the
    approved effective trip factor for operational reporting.
    """
    __tablename__ = "tiom_mis_report"

    report_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(20), index=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    operator_id: Mapped[str | None] = mapped_column(ForeignKey("persons.employee_id"), index=True)
    opening_kmr: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    closing_kmr: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    opening_hmr: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    closing_hmr: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    paper_ref: Mapped[str | None] = mapped_column(String(120), index=True)
    source_document: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    submitted_by: Mapped[str | None] = mapped_column(String(60))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(60))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        Index("ix_tiom_mis_report_lookup", "operating_date", "shift", "vehicle_id", "status"),
    )


class TiomMisTripRow(Base):
    __tablename__ = "tiom_mis_trip_row"

    row_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("tiom_mis_report.report_id"), index=True)
    row_no: Mapped[int] = mapped_column(Integer)
    loading_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    unloading_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    material_raw: Mapped[str | None] = mapped_column(String(120), index=True)
    source_raw: Mapped[str | None] = mapped_column(String(160))
    destination_raw: Mapped[str | None] = mapped_column(String(160))
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("report_id", "row_no", name="uq_tiom_mis_report_row"),)


class TiomTripFactor(Base):
    """Effective-dated trip quantity rules used by TIOM MIS reports.

    Example: OB = 40 MT/trip. The factor is snapshotted into each MIS row
    detail so later rule changes do not rewrite historical reports.
    """
    __tablename__ = "tiom_trip_factor"

    factor_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    material_code: Mapped[str] = mapped_column(String(60), index=True)
    factor_mt_per_trip: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(String(300))
    entered_by: Mapped[str] = mapped_column(String(60), default="SYSTEM")
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (Index("ix_tiom_trip_factor_lookup", "material_code", "effective_from", "effective_to", "active"),)


class TiomMisTripDetail(Base):
    """Canonical master mapping and quantity snapshot for a paper MIS trip row."""
    __tablename__ = "tiom_mis_trip_detail"

    row_id: Mapped[str] = mapped_column(ForeignKey("tiom_mis_trip_row.row_id"), primary_key=True)
    machine_id: Mapped[str | None] = mapped_column(ForeignKey("equipment.machine_id"), index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("products.product_id"), index=True)
    source_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.location_id"), index=True)
    destination_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.location_id"), index=True)
    factor_mt_per_trip: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    calculated_qty_mt: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TiomLocationRole(Base):
    """ERP role classification for one canonical Location master record."""
    __tablename__ = "tiom_location_role"

    role_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.location_id"), index=True)
    role: Mapped[str] = mapped_column(String(20), index=True)  # SOURCE / DESTINATION
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    entered_by: Mapped[str] = mapped_column(String(60), default="SYSTEM")
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("location_id", "role", name="uq_tiom_location_role"),
    )


class TiomWbCanonical(Base):
    """1:1 ERP canonical mapping for legacy/raw WB movement fields."""
    __tablename__ = "tiom_wb_canonical"

    movement_key: Mapped[str] = mapped_column(ForeignKey("wb_movement.movement_key"), primary_key=True)
    source_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.location_id"), index=True)
    destination_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.location_id"), index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("products.product_id"), index=True)
    mapping_status: Mapped[str] = mapped_column(String(40), default="UNMAPPED", index=True)
    normalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TiomLeadDistance(Base):
    """Approved TIOM haul lead master by source area, bench RL, destination and WB path."""
    __tablename__ = "tiom_lead_distance"

    lead_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    source_location_id: Mapped[str] = mapped_column(ForeignKey("locations.location_id"), index=True)
    bench_rl_m: Mapped[int] = mapped_column(Integer, index=True)
    destination_location_id: Mapped[str] = mapped_column(ForeignKey("locations.location_id"), index=True)
    route_mode: Mapped[str] = mapped_column(String(20), index=True)  # WITH_WB / WITHOUT_WB
    lead_km: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    material_scope: Mapped[str | None] = mapped_column(String(30), index=True)
    source_document: Mapped[str | None] = mapped_column(String(180))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    entered_by: Mapped[str] = mapped_column(String(60), default="SYSTEM")
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint(
            "source_location_id", "bench_rl_m", "destination_location_id", "route_mode",
            name="uq_tiom_lead_route"
        ),
        Index("ix_tiom_lead_lookup", "source_location_id", "bench_rl_m", "destination_location_id", "route_mode", "active"),
    )


class TiomMisTripLead(Base):
    """Lead-distance snapshot used by one submitted/draft MIS trip row."""
    __tablename__ = "tiom_mis_trip_lead"

    row_id: Mapped[str] = mapped_column(ForeignKey("tiom_mis_trip_row.row_id"), primary_key=True)
    bench_rl_m: Mapped[int | None] = mapped_column(Integer, index=True)
    route_mode: Mapped[str | None] = mapped_column(String(20), index=True)
    lead_km: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    lead_rule_id: Mapped[str | None] = mapped_column(ForeignKey("tiom_lead_distance.lead_id"), index=True)
    lead_status: Mapped[str] = mapped_column(String(30), default="NOT_CONFIGURED", index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TiomHsdReceiptDetail(Base):
    """TIOM management fields layered on the existing FIFO HSD purchase lot."""
    __tablename__ = "tiom_hsd_receipt_detail"

    lot_id: Mapped[str] = mapped_column(ForeignKey("hsd_purchase_lot.lot_id"), primary_key=True)
    operating_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str | None] = mapped_column(String(20), index=True)
    receipt_type: Mapped[str] = mapped_column(String(20), default="RECEIPT", index=True)
    discount_per_l: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    remarks: Mapped[str | None] = mapped_column(String(300))
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TiomHsdIssueDetail(Base):
    """Meter delta / efficiency snapshot for each TIOM HSD issue."""
    __tablename__ = "tiom_hsd_issue_detail"

    issue_id: Mapped[str] = mapped_column(ForeignKey("hsd_issue.issue_id"), primary_key=True)
    previous_meter_reading: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    usage: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    efficiency: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    efficiency_unit: Mapped[str | None] = mapped_column(String(20))
    entered_by: Mapped[str] = mapped_column(String(60))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TiomMisReconciliation(Base):
    __tablename__ = "tiom_mis_reconciliation"

    reconciliation_id: Mapped[str] = mapped_column(String(70), primary_key=True)
    row_id: Mapped[str] = mapped_column(ForeignKey("tiom_mis_trip_row.row_id"), unique=True, index=True)
    field_trip_id: Mapped[str | None] = mapped_column(ForeignKey("load_trip.trip_id"), index=True)
    wb_movement_key: Mapped[str | None] = mapped_column(ForeignKey("wb_movement.movement_key"), index=True)
    match_status: Mapped[str] = mapped_column(String(40), index=True)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(Text)
    reconciled_by: Mapped[str] = mapped_column(String(60))
    reconciled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(60))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(Text)

MULTISITE_TABLES = [
    Site,
    SiteShift,
    UserSiteAccess,
    UserPermission,
    PersonSiteAssignment,
    EquipmentSiteAssignment,
    SiteLocation,
    SiteMaterial,
    MasterImportBatch,
    MasterImportRow,
    SiteTrip,
    SiteOperationalImportBatch,
    SiteOperationalImportRow,
    SiteWbImportBatch,
    SiteWbMovement,
    SiteWeightFactor,
    SiteHsdTransaction,
    SitePersonAttendance,
    SiteAssetAttendance,
    SiteDeployment,
    SiteAssetMeter,
    SiteTripReconciliation,
    SiteSurveyMeasurement,
    SiteBillingReconciliation,
    SiteDataQualityIssue,
    SiteSatelliteObservation,
    TiomSourceDeployment,
    TiomShiftProductionReport,
    TiomShiftProductionMovement,
    TiomShiftReportBaseline,
    TiomMisReport,
    TiomMisTripRow,
    TiomTripFactor,
    TiomMisTripDetail,
    TiomLocationRole,
    TiomWbCanonical,
    TiomLeadDistance,
    TiomMisTripLead,
    TiomHsdReceiptDetail,
    TiomHsdIssueDetail,
    TiomMisReconciliation,
    SiteAuditLog,
]


def create_multisite_tables(engine) -> None:
    """Create additive v0.9 tables only; never mutate legacy v0.8 tables."""
    for model in MULTISITE_TABLES:
        model.__table__.create(engine, checkfirst=True)
