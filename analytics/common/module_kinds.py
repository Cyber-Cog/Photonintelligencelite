"""Classify analytics modules as fault detectors vs analysis / diagnostics tools.

Box plot and similar distribution tools must never be framed as faults: they do not
belong in fault findings tables, owner-action fault cards, or "Fault modules" UI.
"""
from __future__ import annotations

from typing import Literal

ModuleKind = Literal["fault", "analysis", "kpi"]

# Distribution / comparison tools — not fault detectors.
ANALYSIS_ALGORITHM_IDS: frozenset[str] = frozenset({"box_plot"})

# Plant rollups (not listed in Diagnostics fault folder as a fault).
KPI_ALGORITHM_IDS: frozenset[str] = frozenset({"kpis"})

# Codex-style fault / loss modules shown under Diagnostics → Fault modules.
# string_outlier is intentionally omitted (disabled / not product-facing).
FAULT_ALGORITHM_IDS: frozenset[str] = frozenset(
    {
        "disconnected_strings",
        "clipping_power",
        "clipping_current",
        "inverter_efficiency",
        "module_damage",
    }
)


def module_kind(algorithm_id: str) -> ModuleKind:
    if algorithm_id in ANALYSIS_ALGORITHM_IDS:
        return "analysis"
    if algorithm_id in KPI_ALGORITHM_IDS:
        return "kpi"
    if algorithm_id in FAULT_ALGORITHM_IDS:
        return "fault"
    # Unknown registered algorithms default to fault-style listing for safety.
    return "fault"


def is_analysis_module(algorithm_id: str) -> bool:
    return module_kind(algorithm_id) == "analysis"


def is_fault_module(algorithm_id: str) -> bool:
    return module_kind(algorithm_id) == "fault"
