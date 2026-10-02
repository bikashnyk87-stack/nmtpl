from datetime import datetime
from sqlalchemy import String, DateTime, JSON, ForeignKey
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

TABLES = [VolvoVehicle.__table__, VolvoReport.__table__, VolvoMapping.__table__, VolvoAudit.__table__, VolvoSync.__table__]
