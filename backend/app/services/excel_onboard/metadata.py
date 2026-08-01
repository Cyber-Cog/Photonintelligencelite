"""Phase 4 — Extract header/equipment metadata for AI (never measurements)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.app.services.excel_onboard.analyzer import WorkbookAnalysis
from backend.app.services.excel_onboard.header_recon import HeaderReconstruction
from backend.app.services.excel_onboard.normalizer import NormalizedSheet


@dataclass
class HeaderMetadataPayload:
    """Compact payload safe to send to AI — no measurement rows."""

    workbook: dict[str, Any]
    sheet_name: str
    header_depth: int
    first_data_row: int
    columns: list[dict[str, Any]] = field(default_factory=list)
    equipment_hints: list[str] = field(default_factory=list)
    unknown_tags: list[str] = field(default_factory=list)
    n_data_rows_estimate: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def prompt_json(self) -> dict[str, Any]:
        """Even smaller subset for Gemini prompts."""
        return {
            "sheet_name": self.sheet_name,
            "header_depth": self.header_depth,
            "n_columns": len(self.columns),
            "n_data_rows_estimate": self.n_data_rows_estimate,
            "columns": [
                {
                    "name": c["reconstructed_name"],
                    "parts": c.get("hierarchy_parts") or [],
                    "unit": c.get("unit"),
                    "level_hint": c.get("level_hint"),
                    "equipment_hint": c.get("equipment_hint"),
                    "is_timestamp": c.get("is_timestamp"),
                }
                for c in self.columns[:250]
            ],
            "equipment_hints": self.equipment_hints[:80],
            "unknown_tags": self.unknown_tags[:40],
            "merged_range_count": len(
                ((self.workbook.get("sheets") or [{}])[0] or {}).get("merged_ranges") or []
            )
            if self.workbook
            else 0,
        }


def extract_header_metadata(
    *,
    analysis: WorkbookAnalysis,
    normalized: NormalizedSheet,
    headers: HeaderReconstruction,
) -> HeaderMetadataPayload:
    equip = sorted(
        {
            c.equipment_hint
            for c in headers.columns
            if c.equipment_hint and not c.is_timestamp
        }
    )
    unknown: list[str] = []
    for c in headers.columns:
        if c.is_timestamp:
            continue
        joined = " ".join(c.hierarchy_parts)
        if joined and not c.level_hint and not c.equipment_hint:
            unknown.append(c.reconstructed_name)

    sheet_meta = next((s for s in analysis.sheets if s.sheet_name == normalized.sheet_name), None)
    n_data = max(0, len(normalized.matrix) - headers.first_data_row)

    return HeaderMetadataPayload(
        workbook=analysis.to_dict(),
        sheet_name=normalized.sheet_name,
        header_depth=len(headers.header_row_indexes) or (sheet_meta.header_depth_estimate if sheet_meta else 1),
        first_data_row=headers.first_data_row,
        columns=[asdict(c) for c in headers.columns],
        equipment_hints=equip,
        unknown_tags=unknown[:40],
        n_data_rows_estimate=n_data,
    )
