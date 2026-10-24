"""Typed validation for site Equipment/Vehicle Excel imports.

The source workbook may contain two separately labelled capacities in one
"Bucket CuM" cell, e.g. '31 CUM (HIP VOLUME)/40.30 MT'. Only explicitly
labelled quantities are split; unknown text is a row-level validation error,
not a request-wide server exception. Original cells stay in the staged JSON.
"""
from decimal import Decimal, InvalidOperation
import re

_N=r"(?:\d+(?:\.\d+)?|\.\d+)"
_CUM=r"(?:CUM|CU\.?\s*M|M3|M³)"
_MT=r"(?:MT|METRIC\s*TONNES?|TONNES?|TONS?|T)"
_NUMBER=re.compile(rf"^\s*({_N})\s*$",re.I)
_BUCKET=re.compile(rf"^\s*({_N})\s*{_CUM}\s*$",re.I)
_PAYLOAD=re.compile(rf"^\s*({_N})\s*{_MT}\s*$",re.I)
_COMBINED=re.compile(rf"^\s*({_N})\s*{_CUM}\s*(?:\([^)]{{1,100}}\)\s*)?[/;,]\s*({_N})\s*{_MT}\s*$",re.I)

_MAX_LENGTH={
    "Machine ID":50,"Type":60,"Group":30,"Door No":50,
    "Registration No":50,"Vehicle No":50,"Make Model":120,
    "Ownership":30,"Party":120,
}


def _number(token,label):
    try:
        d=Decimal(str(token))
        if not d.is_finite() or d<=0:
            raise InvalidOperation("must be positive")
        return float(d)
    except (InvalidOperation,ValueError,TypeError,OverflowError) as exc:
        raise ValueError(f"{label} must be a positive numeric quantity.") from exc


def equipment_dimensions(item):
    """Return (bucket_cum, rated_payload_t, was_split).

    Never interpret an unlabelled second value as payload, and never replace
    an explicit rated payload by a contradictory embedded MT figure.
    """
    raw_bucket=item.get("Bucket CuM")
    raw_payload=item.get("Rated Payload T")
    bucket=embedded_mt=None
    split=False
    if raw_bucket not in (None,""):
        raw=str(raw_bucket).strip()
        pair=_COMBINED.fullmatch(raw)
        if pair:
            bucket=_number(pair.group(1),"Bucket CuM")
            embedded_mt=_number(pair.group(2),"Rated Payload T")
            split=True
        else:
            match=_NUMBER.fullmatch(raw) or _BUCKET.fullmatch(raw)
            if not match:
                raise ValueError(
                    f"Bucket CuM '{raw[:80]}' is not a valid cubic-metre value. "
                    "Use e.g. 3.5 or '31 CUM (HIP VOLUME)/40.30 MT'."
                )
            bucket=_number(match.group(1),"Bucket CuM")
    explicit_mt=None
    if raw_payload not in (None,""):
        raw=str(raw_payload).strip()
        match=_NUMBER.fullmatch(raw) or _PAYLOAD.fullmatch(raw)
        if not match:
            raise ValueError(
                f"Rated Payload T '{raw[:80]}' is not a valid metric-tonne value. "
                "Use e.g. 40.30 or '40.30 MT'."
            )
        explicit_mt=_number(match.group(1),"Rated Payload T")
    if embedded_mt is not None and explicit_mt is not None and abs(embedded_mt-explicit_mt)>0.001:
        raise ValueError(
            f"Rated Payload T {explicit_mt:g} conflicts with {embedded_mt:g} MT "
            "in Bucket CuM. Correct the workbook before importing."
        )
    return bucket,(explicit_mt if explicit_mt is not None else embedded_mt),split


def equipment_row_errors(item,master_type):
    errors=[]
    for field,width in _MAX_LENGTH.items():
        val=item.get(field)
        if val not in (None,"") and len(str(val).strip())>width:
            errors.append(f"{field} exceeds {width} characters")
    if master_type in {"EQUIPMENT","VEHICLE"}:
        try:
            equipment_dimensions(item)
        except ValueError as exc:
            errors.append(str(exc))
    return errors
