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


def score_column(column_name: str) -> ColumnCandidate:
    if _is_garbage_header(column_name) or _is_ambiguous_column(column_name):
        return ColumnCandidate(column_name, None, 0.0, None)

    # Plant-level totals are not per-inverter AC/DC — never auto-map them into those slots.
    n_raw = _normalize(column_name)
    if n_raw.startswith("plant") and any(x in n_raw for x in ("ac", "dc", "power")):
        return ColumnCandidate(column_name, None, 0.0, None)

    lookup = _alias_lookup()
    normalized = n_raw

    if normalized in lookup:
        return ColumnCandidate(column_name, lookup[normalized], 1.0, normalized)

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
