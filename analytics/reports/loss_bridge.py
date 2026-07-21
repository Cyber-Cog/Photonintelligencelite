"""Loss energy bridge for PDF/Excel reports — mirrors frontend buildLossBridge."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from analytics.core.result import ResultObject, ResultStatus

_DIAG_ORDER = {
    "inverter_efficiency": 10,
    "clipping_power": 20,
    "clipping_current": 30,
    "disconnected_strings": 40,
    "module_damage": 50,
    "string_outlier": 60,
}

_DIAG_LABELS = {
    "inverter_efficiency": "Inverter efficiency",
    "clipping_power": "Clipping (power)",
    "clipping_current": "Clipping (current)",
    "disconnected_strings": "Disconnected strings",
    "module_damage": "Module damage / diode",
    "string_outlier": "String outlier",
}


@dataclass
class BridgeSegment:
    key: str
    label: str
    invisible: float
    visible: float
    kind: str  # total | loss | unknown
    raw_mwh: float


@dataclass
class BridgeModel:
    mode: str  # bridge | categories
    expected_mwh: float
    actual_mwh: float
    unknown_mwh: float
    diagnosed_mwh: float
    segments: list[BridgeSegment]
    note: str | None


def _kwh_to_mwh(kwh: float) -> float:
    return kwh / 1000.0


def _diagnosed_losses(results: list[ResultObject]) -> list[tuple[str, str, float]]:
    rows: list[tuple[str, str, float]] = []
    for r in results:
        if r.status != ResultStatus.OK:
            continue
        loss = r.loss_energy_kwh or 0.0
        if loss <= 1e-6:
            continue
        rows.append(
            (
                r.algorithm_id,
                _DIAG_LABELS.get(r.algorithm_id, r.title),
                _kwh_to_mwh(loss),
            )
        )
    rows.sort(key=lambda x: (_DIAG_ORDER.get(x[0], 100), -x[2]))
    return rows


def _categories_note(actual_kwh: Any, pr: Any) -> str:
    """Plain-text note for PDF/Excel (no UI links)."""
    has_actual = actual_kwh is not None and isinstance(actual_kwh, (int, float)) and actual_kwh > 0
    has_pr = pr is not None and isinstance(pr, (int, float)) and pr > 0
    if not has_actual and not has_pr:
        return (
            "Actual energy and Performance Ratio unavailable — map inverter AC power, "
            "POA/GHI, and plant DC capacity, then re-run. Showing diagnosed loss categories only."
        )
    if not has_actual:
        return "Actual energy unavailable — map inverter AC power and re-run. Showing diagnosed loss categories only."
    if not has_pr:
        return (
            "Expected energy unavailable (Performance Ratio missing) — ensure plant DC capacity "
            "and POA/GHI are set, then re-run. Showing diagnosed loss categories only."
        )
    return "Expected / actual energy unavailable — showing diagnosed loss categories only."


def build_loss_bridge(kpis: dict[str, Any], results: list[ResultObject]) -> BridgeModel | None:
    """Build Expected → diagnosed losses → Unknown → Actual bridge (MWh)."""
    cats = _diagnosed_losses(results)
    diagnosed_mwh = sum(c[2] for c in cats)
    actual_kwh = kpis.get("total_ac_energy_kwh")
    pr = kpis.get("performance_ratio_pct")

    can_bridge = (
        actual_kwh is not None
        and actual_kwh > 0
        and pr is not None
        and pr > 0
        and isinstance(pr, (int, float))
    )

    if not can_bridge and not cats:
        return None

    if not can_bridge:
        cum = diagnosed_mwh
        segments: list[BridgeSegment] = []
        for algo_id, label, mwh in cats:
            cum -= mwh
            segments.append(
                BridgeSegment(
                    key=f"diag_{algo_id}",
                    label=label,
                    invisible=max(0.0, cum),
                    visible=mwh,
                    kind="loss",
                    raw_mwh=mwh,
                )
            )
        return BridgeModel(
            mode="categories",
            expected_mwh=0.0,
            actual_mwh=0.0,
            unknown_mwh=0.0,
            diagnosed_mwh=diagnosed_mwh,
            segments=segments,
            note=_categories_note(actual_kwh, pr),
        )

    actual_mwh = _kwh_to_mwh(float(actual_kwh))
    expected_mwh = actual_mwh / (float(pr) / 100.0)
    unknown_mwh = max(0.0, expected_mwh - actual_mwh - diagnosed_mwh)
    overlap = (
        "Diagnosed losses may overlap across modules; unknown is clamped at zero."
        if expected_mwh - actual_mwh - diagnosed_mwh < -1e-6
        else None
    )

    segments = [
        BridgeSegment(
            key="expected",
            label="Expected energy",
            invisible=0.0,
            visible=expected_mwh,
            kind="total",
            raw_mwh=expected_mwh,
        )
    ]
    cum = expected_mwh
    for algo_id, label, mwh in cats:
        cum -= mwh
        segments.append(
            BridgeSegment(
                key=f"diag_{algo_id}",
                label=label,
                invisible=max(0.0, cum),
                visible=mwh,
                kind="loss",
                raw_mwh=mwh,
            )
        )
    segments.append(
        BridgeSegment(
            key="unknown",
            label="Unknown loss",
            invisible=actual_mwh,
            visible=unknown_mwh,
            kind="unknown",
            raw_mwh=unknown_mwh,
        )
    )
    segments.append(
        BridgeSegment(
            key="actual",
            label="Actual energy (metered)",
            invisible=0.0,
            visible=actual_mwh,
            kind="total",
            raw_mwh=actual_mwh,
        )
    )

    return BridgeModel(
        mode="bridge",
        expected_mwh=expected_mwh,
        actual_mwh=actual_mwh,
        unknown_mwh=unknown_mwh,
        diagnosed_mwh=diagnosed_mwh,
        segments=segments,
        note=overlap,
    )
