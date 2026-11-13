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


def kocp_equipment_category(asset_type: str | None, make_model: str | None = None) -> str:
    """Canonical *physical* category. Never confuse Coal/OB group or ownership."""
    typ = str(asset_type or "").upper()
    model = str(make_model or "").upper()
    # The L150H wheel loader has accidentally been called 'Tripper' in masters.
    if "L150H" in model or "L150H" in typ or "LOADER" in typ or "LOADER" in model:
        return "LOADER"
    if any(k in typ + " " + model for k in ("EXCAVATOR", "EC480", "BACKHOE", "HITACHI")):
        return "EXCAVATOR"
    if any(k in typ for k in ("TIPPER", "TRIPPER", "DUMPER")):
        return "TIPPER"
    if "DOZER" in typ: return "DOZER"
    if "GRADER" in typ: return "GRADER"
    if "DRILL" in typ: return "DRILL"
    if "TANKER" in typ: return "TANKER"
    if any(k in typ for k in ("BOLERO", "PICK", "CAR", "VAN", "SUV", "BIKE", "HERO", "TVS")):
        return "LMV"
    return "OTHER"


def kocp_ownership_category(ownership: str | None) -> str:
    raw = str(ownership or "").strip().upper()
    if raw in {"OWN", "OWNED", "NMTPL", "COMPANY", "OWN VEHICLE"}:
        return "OWN"
    if raw in {"HIRED", "HIRE", "RENTED", "RENTAL"}:
        return "HIRED"
    return "THIRD PARTY" if raw else "UNSPECIFIED"


def kocp_vehicle_classes(asset_type: str | None, group: str | None = None,
                          make_model: str | None = None) -> set[str]:
    """Matches exact legacy type AND controlled brand/type classes for factors."""
    text = " ".join((str(asset_type or ""), str(make_model or ""))).upper()
    classes = {str(asset_type or "").strip().upper(), str(group or "").strip().upper()}
    category = kocp_equipment_category(asset_type, make_model)
    classes.add(category)
    for brand in ("EICHER", "TATA", "BHARAT BENZ", "VOLVO", "ASHOK LEYLAND"):
        if brand in text:
            classes.add(brand)
            classes.add(brand + " " + category)
    if "BENZ" in text: classes.add("BHARAT BENZ")
    return {x for x in classes if x}


def kocp_role_allowed(asset_type: str | None, role: str,
                      make_model: str | None = None) -> bool:
    category = kocp_equipment_category(asset_type, make_model)
    role = str(role or "").strip().upper()
    if role == "LOADING": return category in {"LOADER", "EXCAVATOR"}
    if role == "TRANSPORT": return category == "TIPPER"
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
