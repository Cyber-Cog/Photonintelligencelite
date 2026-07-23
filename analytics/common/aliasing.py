"""Column alias detection with confidence scoring.

Confidence bands (see docs/PRD.md §7.4):
  >= 0.90  -> map automatically, no user interaction
  0.60-0.89 -> map automatically, but surface a dismissible confirmation
  < 0.60 or no candidate -> route to the manual mapping wizard
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from analytics.common.config_loader import load_aliases

HIGH_CONFIDENCE = 0.90
MEDIUM_CONFIDENCE = 0.60

# OEM columns like "SMB01 Current", "SCB_12_Idc", "String 3 Current (A)" that aliases.yaml
# cannot enumerate exhaustively. Exact YAML aliases still win (confidence 1.0).
_PATTERN_DC_CURRENT = re.compile(
    r"^(?:(?:inv(?:erter)?\s*\d+\s*)?(?:smb|scb|string|str|combiner(?:\s*box)?|mppt)\s*\d*\s*"
    r"(?:current|idc|i\s*dc|amps?)(?:\s*(?:a|amp|amps))?|"
    r"(?:current|idc)\s*(?:smb|scb|string|str|combiner|mppt)\s*\d*)$"
)
_PATTERN_DC_VOLTAGE = re.compile(
    r"^(?:(?:inv(?:erter)?\s*\d+\s*)?(?:smb|scb|string|str|combiner(?:\s*box)?|mppt)\s*\d*\s*"
    r"(?:voltage|vdc|v\s*dc)(?:\s*(?:v|volt|volts))?|"
    r"(?:voltage|vdc)\s*(?:smb|scb|string|str|combiner|mppt)\s*\d*)$"
)
_PATTERN_SCB_ID = re.compile(
    r"^(?:smb|scb|combiner(?:\s*box)?)\s*(?:id|no|number|#)?\s*\d*$"
)


def _normalize(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[\(\)\[\]{}]", " ", s)
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


@dataclass(frozen=True)
class ColumnCandidate:
    column_name: str
    canonical_field: str | None
    confidence: float
    matched_alias: str | None = None


def _alias_lookup() -> dict[str, str]:
    """normalized alias -> canonical field, built once per call (cheap; aliases.yaml is small)."""
    out: dict[str, str] = {}
    for canonical_field, aliases in load_aliases().items():
        for alias in aliases:
            out[_normalize(alias)] = canonical_field
    return out


AMBIGUOUS_COLUMN_DENYLIST = frozenset({"pr", "status", "alarm", "availability", "availability pct"})


def _is_garbage_header(column_name: str) -> bool:
    """Blank / Excel Unnamed headers must never auto-map (especially as timestamp)."""
    n = _normalize(column_name)
    return not n or n.startswith("unnamed") or n.startswith("column ")


def _is_ambiguous_column(column_name: str) -> bool:
    n = _normalize(column_name)
    return n in AMBIGUOUS_COLUMN_DENYLIST or len(n) <= 2


def _pattern_canonical(normalized: str) -> tuple[str, str] | None:
    """Return (canonical_field, matched_pattern_label) for OEM numbered SMB/SCB headers."""
    if _PATTERN_DC_CURRENT.match(normalized):
        return "dc_current_a", "pattern:smb/scb/string current"
    if _PATTERN_DC_VOLTAGE.match(normalized):
        return "dc_voltage_v", "pattern:smb/scb/string voltage"
    if _PATTERN_SCB_ID.match(normalized) and not normalized.endswith(("current", "voltage", "power")):
        # Bare "smb" / "scb" are exact aliases; numbered ids like "smb 01" land here.
        if re.search(r"\d", normalized):
            return "scb_id", "pattern:smb/scb id"
    return None


def score_column(column_name: str) -> ColumnCandidate:
    if _is_garbage_header(column_name):
        return ColumnCandidate(column_name, None, 0.0, None)

    # Plant-level totals are not per-inverter AC/DC — never auto-map them into those slots.
    n_raw = _normalize(column_name)
    if n_raw.startswith("plant") and any(x in n_raw for x in ("ac", "dc", "power")):
        return ColumnCandidate(column_name, None, 0.0, None)

    lookup = _alias_lookup()
    normalized = n_raw

    # Exact YAML aliases win first — including intentional short aliases like "i" / "v" / "p".
    # Ambiguous-length blocking applies only to fuzzy matching below.
    if normalized in lookup:
        return ColumnCandidate(column_name, lookup[normalized], 1.0, normalized)

    patterned = _pattern_canonical(normalized)
    if patterned is not None:
        field, label = patterned
        return ColumnCandidate(column_name, field, 0.97, label)

    if _is_ambiguous_column(column_name):
        return ColumnCandidate(column_name, None, 0.0, None)

    # Fuzzy match against every known alias; scale similarity into our confidence bands so an
    # exact match beats near-exact and near-exact still clears the auto-confirm threshold.
    best_field: str | None = None
    best_alias: str | None = None
    best_ratio = 0.0
    for alias_norm, field_name in lookup.items():
        ratio = difflib.SequenceMatcher(None, normalized, alias_norm).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_field = field_name
            best_alias = alias_norm

    if best_field is None or best_ratio < 0.55:
        return ColumnCandidate(column_name, None, 0.0, None)

    # Map [0.55, 1.0) similarity -> [0.55, 0.98) confidence, leaving 1.0 reserved for exact matches.
    confidence = 0.55 + (best_ratio - 0.55) * (0.43 / 0.45)
    return ColumnCandidate(column_name, best_field, round(min(confidence, 0.98), 3), best_alias)


def score_columns(column_names: list[str]) -> list[ColumnCandidate]:
    """Score every column, then resolve conflicts that would poison analysis.

    Plant-level totals (PlantAC_MW, PlantDC_MW) must not steal the inverter AC/DC
    slots when a true per-inverter power column is present — that made efficiency
    compare INV AC against plant-wide DC and look like ~20% conversion.
    """
    scored = [score_column(name) for name in column_names]
    norms = {_normalize(c.column_name): c for c in scored}

    has_inverter_ac = any(
        c.canonical_field == "ac_power_kw"
        and "plant" not in _normalize(c.column_name)
        and c.confidence >= MEDIUM_CONFIDENCE
        for c in scored
    )
    has_inverter_dc = any(
        c.canonical_field == "dc_power_kw"
        and "plant" not in _normalize(c.column_name)
        and c.confidence >= MEDIUM_CONFIDENCE
        for c in scored
    )

    out: list[ColumnCandidate] = []
    for c in scored:
        n = _normalize(c.column_name)
        if "plant" in n and c.canonical_field == "ac_power_kw" and has_inverter_ac:
            out.append(ColumnCandidate(c.column_name, None, 0.0, None))
            continue
        if "plant" in n and c.canonical_field == "dc_power_kw" and (has_inverter_ac or has_inverter_dc):
            # Plant DC is a plant total — not usable as per-inverter DC for efficiency.
            out.append(ColumnCandidate(c.column_name, None, 0.0, None))
            continue
        out.append(c)
    return out


def confidence_band(confidence: float) -> str:
    if confidence >= HIGH_CONFIDENCE:
        return "auto"
    if confidence >= MEDIUM_CONFIDENCE:
        return "confirm"
    return "manual"
