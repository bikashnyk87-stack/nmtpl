from __future__ import annotations
from datetime import date
from app.models import ShiftRotation
from app.services.time_context import week_monday


def resolve_rotation_shift(rotation: ShiftRotation, operating_date: date) -> str:
    team_id = str(getattr(rotation, "team_id", "") or "").strip().upper()
    fixed = {"TEAM-A": "A", "TEAM-B": "B", "TEAM-C": "C"}
    if team_id in fixed:
        return fixed[team_id]

    pattern = [x.strip().upper() for x in rotation.rotation_pattern.split(",") if x.strip()]
    if not pattern:
        raise ValueError("Rotation pattern is empty")
    anchor_shift = rotation.anchor_shift.strip().upper()
    if anchor_shift not in pattern:
        raise ValueError(f"Anchor shift {anchor_shift} is not in rotation pattern")
    target_monday = week_monday(operating_date)
    weeks = (target_monday - rotation.anchor_monday).days // 7
    start = pattern.index(anchor_shift)
    return pattern[(start + weeks) % len(pattern)]
