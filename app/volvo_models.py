from datetime import datetime
from sqlalchemy import String, DateTime, JSON, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class VolvoVehicle(Base):
    __tablename__ = 'volvo_vehicle'
    vin: Mapped[str] = mapped_column(String(17), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class VolvoReport(Base):
    __tablename__ = 'volvo_report'
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    vin: Mapped[str] = mapped_column(String(17), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)

class VolvoMapping(Base):
    __tablename__ = 'volvo_mapping'
    vin: Mapped[str] = mapped_column(ForeignKey('volvo_vehicle.vin'), primary_key=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey('equipment.machine_id'), unique=True)
    changed_by: Mapped[str] = mapped_column(String(60))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class VolvoAudit(Base):
    __tablename__ = 'volvo_mapping_audit'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vin: Mapped[str] = mapped_column(String(17))
    old_machine_id: Mapped[str | None] = mapped_column(String(50))
    new_machine_id: Mapped[str | None] = mapped_column(String(50))
    actor: Mapped[str] = mapped_column(String(60))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class VolvoSync(Base):
    __tablename__ = 'volvo_sync'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    counts: Mapped[dict] = mapped_column(JSON)


class VolvoLocationZone(Base):
    """GPS geofence for an existing TIOM Location Master row.

    Kept separate from the ERP Location Master so Volvo/GPS configuration does
    not alter operational master semantics.
    """
    __tablename__ = 'volvo_location_zone'
    location_id: Mapped[str] = mapped_column(ForeignKey('locations.location_id'), primary_key=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_m: Mapped[float] = mapped_column(Float, nullable=False, default=300.0)
    changed_by: Mapped[str] = mapped_column(String(60))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


TABLES = [
    VolvoVehicle.__table__, VolvoReport.__table__, VolvoMapping.__table__,
    VolvoAudit.__table__, VolvoSync.__table__, VolvoLocationZone.__table__,
]
