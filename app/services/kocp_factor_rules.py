"""KOCP approved per-trip quantity rule selection.

Do not default an unloading point to a mine-wide factor. A route-specific
factor outranks a destination-wide factor; missing and equally-specific
conflicting rules are blocked rather than guessed.
"""
from __future__ import annotations

from datetime import date
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.site_models import SiteWeightFactor


def _norm(value):
    return " ".join(str(value or "").upper().split())


def choose_point_factor(
    candidates, *, operating_day: date, shift: str,
    destination_id: str, route_id: str | None, material_id: str,
    vehicle_type: str | None = None, vehicle_group: str | None = None,
):
    """Pure deterministic selection, convenient for testing and imports."""
    matches = []
    for factor in candidates:
        if factor.status != "APPROVED" or factor.effective_from > operating_day:
            continue
        if factor.effective_to and factor.effective_to < operating_day:
            continue
        if factor.operating_date and factor.operating_date != operating_day:
            continue
        # Mandatory point scope: no unscoped mine-wide default.
        if not factor.destination_location_id or factor.destination_location_id != destination_id:
            continue
        if factor.route_id and factor.route_id != route_id:
            continue
        if factor.material_id and factor.material_id != material_id:
            continue
        if factor.shift and _norm(factor.shift) != _norm(shift):
            continue
        if factor.vehicle_class and _norm(factor.vehicle_class) not in {
            _norm(vehicle_type), _norm(vehicle_group),
        }:
            continue
        # Route specificity, material, shift and class all have explicit priority.
        score = (
            int(bool(factor.route_id)),
            int(bool(factor.material_id)),
            int(bool(factor.shift)),
            int(bool(factor.vehicle_class)),
            int(bool(factor.operating_date)),
            factor.effective_from.toordinal(),
        )
        matches.append((score, factor))
    if not matches:
        raise HTTPException(
            409, "No approved MCL factor matches this unloading point, route, "
                 "material, vehicle class, operating date and shift. "
                 "Configure the point-wise rule first."
        )
    matches.sort(key=lambda x: x[0], reverse=True)
    top_score = matches[0][0]
    ties = [row for score, row in matches if score == top_score]
    if len(ties) != 1:
        raise HTTPException(
            409, "Multiple equally applicable approved MCL factors found. "
                 "Resolve duplicate/overlapping rules before saving trips."
        )
    return ties[0]


def resolve_kocp_point_factor(
    db: Session, *, factor_type: str, operating_day: date,
    shift: str, destination_id: str, route_id: str | None,
    material_id: str, vehicle_type: str | None = None,
    vehicle_group: str | None = None,
):
    candidates = db.scalars(select(SiteWeightFactor).where(
        SiteWeightFactor.site_id == "KOCP",
        SiteWeightFactor.factor_type == factor_type,
        SiteWeightFactor.status == "APPROVED",
        SiteWeightFactor.effective_from <= operating_day,
    )).all()
    return choose_point_factor(
        candidates, operating_day=operating_day, shift=shift,
        destination_id=destination_id, route_id=route_id,
        material_id=material_id, vehicle_type=vehicle_type,
        vehicle_group=vehicle_group,
    )
