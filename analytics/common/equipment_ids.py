"""Equipment ID parsing helpers.

Ported (logic only) from PIC's backend/common/helpers.py naming-convention regexes,
generalized to accept both canonical INV-xx-SCB-xx-STR-xx ids and common looser vendor
formats since PIC Lite cannot assume the strict PIC naming convention on arbitrary
customer uploads.
"""
from __future__ import annotations

import re

import pandas as pd

_INVERTER_STRICT = re.compile(r"^INV-\d{1,3}[A-Z]?$", re.IGNORECASE)
_SCB_STRICT = re.compile(r"^INV-\d{1,3}[A-Z]?-(?:SCB|SMB)-\d{1,3}$", re.IGNORECASE)
_STRING_STRICT = re.compile(r"^INV-\d{1,3}[A-Z]?-(?:SCB|SMB)-\d{1,3}-STR-\d{1,3}$", re.IGNORECASE)

# Looser fallback patterns seen across OEM exports (e.g. "Inverter01", "INV_01_SCB_02", "SMB-01").
_SCB_LOOSE = re.compile(r"(INV[-_]?\w+)[-_](SCB|SMB|MPPT)[-_]?(\d+)", re.IGNORECASE)
_SMB_STANDALONE = re.compile(r"^(?:SMB|SCB|COMBINER|CB)[-_\s]?\d+", re.IGNORECASE)
_INVERTER_LOOSE = re.compile(r"(INV(?:ERTER)?)[-_]?(\d+[A-Z]?)", re.IGNORECASE)


def _as_clean_id(equipment_id) -> str | None:
    """Normalize any scalar (including pandas NA) to a stripped id string, or None."""
    try:
        # pd.isna handles None / NaN / pd.NA without `bool(pd.NA)` which raises.
        if equipment_id is None or bool(pd.isna(equipment_id)):
            return None
    except (TypeError, ValueError):
        if equipment_id is None:
            return None
    try:
        eid = str(equipment_id).strip()
    except Exception:
        return None
    if not eid or eid.lower() in {"nan", "<na>", "none", "nat", "null"}:
        return None
    return eid


def derive_level(equipment_id) -> str | None:
    eid = _as_clean_id(equipment_id)
    if eid is None:
        return None
    if _STRING_STRICT.match(eid):
        return "string"
    if _SCB_STRICT.match(eid) or _SCB_LOOSE.search(eid) or _SMB_STANDALONE.match(eid):
        return "scb"
    if _INVERTER_STRICT.match(eid) or _INVERTER_LOOSE.search(eid):
        return "inverter"
    return None


def extract_parent_scb(string_id) -> str | None:
    eid = _as_clean_id(string_id)
    if eid is None:
        return None
    parts = eid.rsplit("-STR-", 1)
    return parts[0] if len(parts) == 2 else None


def extract_parent_inverter(scb_or_string_id) -> str | None:
    eid = _as_clean_id(scb_or_string_id)
    if eid is None:
        return None
    m = _SCB_LOOSE.search(eid)
    if m:
        return m.group(1)
    for marker in ("-SCB-", "-SMB-", "-MPPT-"):
        parts = eid.rsplit(marker, 1)
        if len(parts) == 2:
            return parts[0]
    m2 = _INVERTER_LOOSE.search(eid)
    return m2.group(0) if m2 else None


def resolve_inverter_from_architecture(
    scb_id,
    architecture: dict | None,
) -> str | None:
    """Look up parent inverter for an SCB/SMB id from plant architecture."""
    eid = _as_clean_id(scb_id)
    if eid is None or not architecture:
        return None
    entry = architecture.get(eid)
    if entry is None:
        # Case-insensitive key fallback for OEM exports
        lower_map = {str(k).strip().lower(): v for k, v in architecture.items()}
        entry = lower_map.get(eid.lower())
    if not isinstance(entry, dict):
        return None
    inv = entry.get("inverter_id")
    return _as_clean_id(inv)
