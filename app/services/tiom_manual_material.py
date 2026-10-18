"""Stable aliases for TIOM manual trip-weight material names.

Only *explicit* Sub-grade, Lumps and Boulder labels share the new rules.
Do not assume a source/destination or a product like CLO is a manual Lumps trip.
"""
import re


def canonical_manual_45_material(product_id="", product_name="", material_raw=""):
    combined = " ".join(str(s or "") for s in (product_id, product_name, material_raw))
    tokens = re.sub(r"[^A-Z0-9]+", " ", combined.upper()).strip()
    if re.search(r"\bSUB\s*GRADE\b", tokens):
        return "SUBGRADE"
    if re.search(r"\bBOULDERS?\b", tokens):
        return "BOULDER"
    if re.search(r"\bLUMPS?\b", tokens):
        return "ROM_LUMPS"
    return None
