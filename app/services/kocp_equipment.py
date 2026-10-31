"""Strict, non-mutating KOCP equipment eligibility and field-entry labels.

The Equipment master uses `group` for COAL / OB / OB-COAL (BOTH) / KOCP.
Its `type` describes the physical machine, not the operating material.
Do not infer Coal/OB eligibility from the machine type or registration alone.
"""
from __future__ import annotations
import re


def kocp_asset_allowed(group: str | None, activity: str) -> bool:
    activity = str(activity or "").strip().upper()
    if activity not in {"COAL", "OB"}:
        return False
    labels = set(re.findall(r"[A-Z]+", str(group or "").upper()))
    return activity in labels


def kocp_role_allowed(asset_type: str | None, role: str) -> bool:
    kind = str(asset_type or "").strip().upper()
    role = str(role or "").strip().upper()
    if role == "LOADING":
        return any(x in kind for x in ("LOADER", "EXCAVATOR", "BACKHOE", "HITACHI"))
    if role == "TRANSPORT":
        return any(x in kind for x in ("TRIPPER", "TIPPER", "DUMPER"))
    return False


def kocp_rental_reference(machine_id: str, ownership: str | None) -> str:
    owner = str(ownership or "").strip().upper()
    if owner in {"NMTPL", "OWN", "OWNED"} or not owner:
        return ""
    # Existing unique Machine ID remains the primary key. This is a display
    # reference only, not a new Door No or an invented registration.
    return "R-" + str(machine_id).strip()


def kocp_asset_display(machine_id: str, door_no: str | None,
                       vehicle_no: str | None, ownership: str | None,
                       party: str | None, asset_type: str | None) -> tuple[str, str, str]:
    door = str(door_no or "").strip()
    vehicle = str(vehicle_no or "").strip()
    rental = kocp_rental_reference(machine_id, ownership)
    key = ("Door " + door) if door else (rental or "ID " + str(machine_id))
    label = key + (" · " + vehicle if vehicle else "")
    owner = str(party or ownership or "").strip()
    sub = " · ".join(x for x in (str(asset_type or "").strip(), owner,
                                "ID " + str(machine_id)) if x)
    return label, sub, rental
