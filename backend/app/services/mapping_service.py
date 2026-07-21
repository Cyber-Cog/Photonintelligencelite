"""Column mapping: header inspection, confidence-scored suggestions, and mapping-template
persistence (Postgres stores only the mapping itself, keyed by an OEM/file signature —
never the CSV data). See docs/PRD.md §7.4-7.5, §10.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from analytics.common.aliasing import HIGH_CONFIDENCE, confidence_band, score_columns
from analytics.common.complete_analysis_pack import looks_like_complete_pack, pack_header_overlap
from analytics.core.context import ResolvedMapping
from backend.app.models import MappingTemplate
from backend.app.schemas import ColumnMappingSuggestion

REQUIRED_TIMESTAMP_CONFIDENCE_FIELD = "timestamp"


def read_header(csv_path: Path) -> list[str]:
    sample = pd.read_csv(csv_path, nrows=0)
    return [str(c) for c in sample.columns]


def oem_signature(columns: list[str]) -> str:
    normalized = "|".join(sorted(c.strip().lower() for c in columns))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def detect_pack_match(columns: list[str]) -> tuple[bool, float]:
    """Return (looks_like_complete_pack, overlap_ratio 0..1)."""
    matched, total = pack_header_overlap(columns)
    ratio = (matched / total) if total else 0.0
    return looks_like_complete_pack(columns), round(ratio, 3)


def suggest_mapping(columns: list[str], *, pack_match: bool | None = None) -> list[ColumnMappingSuggestion]:
    """Score every detected column. Never drop columns from the suggestion list.

    When headers do **not** match the Complete Analysis Pack, fuzzy near-misses stay in
    the confirm/manual bands so Setup does not silently treat OEM exports as the pack.
    Exact alias hits (confidence 1.0) still auto-map.
    """
    if pack_match is None:
        pack_match, _ = detect_pack_match(columns)

    candidates = score_columns(columns)
    out: list[ColumnMappingSuggestion] = []
    for c in candidates:
        band = confidence_band(c.confidence)
        # Non-pack uploads: only exact alias matches get silent auto; fuzzy stays reviewable.
        if not pack_match and band == "auto" and c.confidence < 1.0:
            band = "confirm"
        # Pack uploads: boost already-high matches so Setup can auto-map heavily.
        if pack_match and c.canonical_field and c.confidence >= HIGH_CONFIDENCE:
            band = "auto"
        out.append(
            ColumnMappingSuggestion(
                column_name=c.column_name,
                canonical_field=c.canonical_field,
                confidence=c.confidence,
                band=band,
            )
        )
    return out


def requires_manual_mapping(suggestions: list[ColumnMappingSuggestion]) -> bool:
    return any(s.band == "manual" for s in suggestions)


def _sanitize_template_mapping(column_to_canonical: dict[str, str]) -> dict[str, str]:
    """Drop plant-total → inverter AC/DC mappings that poison efficiency."""
    out: dict[str, str] = {}
    for col, field in column_to_canonical.items():
        n = col.strip().lower().replace("_", " ")
        if field in {"ac_power_kw", "dc_power_kw"} and n.startswith("plant"):
            continue
        out[col] = field
    return out


def find_saved_template(db: Session, columns: list[str]) -> dict[str, str] | None:
    signature = oem_signature(columns)
    row = db.query(MappingTemplate).filter(MappingTemplate.oem_signature == signature).first()
    if not row:
        return None
    return _sanitize_template_mapping(dict(row.column_to_canonical_json))


def save_template(db: Session, columns: list[str], column_to_canonical: dict[str, str]) -> None:
    signature = oem_signature(columns)
    cleaned = _sanitize_template_mapping(column_to_canonical)
    row = db.query(MappingTemplate).filter(MappingTemplate.oem_signature == signature).first()
    if row:
        row.column_to_canonical_json = cleaned
        row.use_count += 1
    else:
        row = MappingTemplate(oem_signature=signature, column_to_canonical_json=cleaned)
        db.add(row)
    db.commit()


def resolve_mapping(
    column_to_canonical: dict[str, str],
    confidence_by_column: dict[str, float],
    oem_sig: str | None = None,
) -> ResolvedMapping:
    cleaned = {c: f for c, f in column_to_canonical.items() if f and f != "ignore"}
    return ResolvedMapping(
        column_to_canonical=cleaned,
        confidence_by_column=confidence_by_column,
        detected_oem_signature=oem_sig,
    )


def timestamp_column(column_to_canonical: dict[str, str]) -> str | None:
    for col, field in column_to_canonical.items():
        if field == REQUIRED_TIMESTAMP_CONFIDENCE_FIELD:
            return col
    return None


def overlay_prior_mapping(
    suggestions: list[ColumnMappingSuggestion],
    prior: dict[str, str] | None,
) -> list[ColumnMappingSuggestion]:
    """Preserve prior canonical choices for columns that still exist after re-upload."""
    if not prior:
        return suggestions
    for s in suggestions:
        if s.column_name in prior:
            field = prior[s.column_name]
            if field and field != "ignore":
                s.canonical_field = field
                s.confidence = max(s.confidence, 0.99)
                s.band = "confirm"
            else:
                s.canonical_field = None
                s.confidence = 0.0
                s.band = "manual"
    return suggestions
