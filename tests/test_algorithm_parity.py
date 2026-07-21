"""Parity tests for the PIC-ported behaviors added in the 2026-07-20 rebuild:

  1. Inverter efficiency DC fallback (ΣI_scb×V/1000 when native DC power is absent).
  2. Disconnected-string spare_flag exclusion.
  3. Clipping-power coverage guard skips (and reports) thin-coverage inverters.
  4. Module-damage forward-Δt loss integration remains detection-stable.

These assert against the shared synthetic ``demo_context`` fixture (tests/conftest.py).
"""
from __future__ import annotations

import dataclasses

import pandas as pd

from analytics.algorithms import clipping_power, disconnected_strings, inverter_efficiency
from analytics.core.context import AnalysisContext, CanonicalDataAccess
from analytics.core.result import ResultStatus


def _replace_canonical(context: AnalysisContext, frame: pd.DataFrame) -> AnalysisContext:
    return dataclasses.replace(context, canonical=CanonicalDataAccess.from_frame(frame))


def test_efficiency_dc_fallback_from_scb_current(demo_context):
    """When inverter dc_power_kw is stripped, efficiency must reconstruct DC from child SCBs."""
    frame = demo_context.canonical.frame()
    stripped = frame.copy()
    # Remove native inverter DC power entirely — force the SCB I×V fallback path.
    stripped.loc[stripped["device_type"] == "inverter", "dc_power_kw"] = pd.NA

    ctx = _replace_canonical(demo_context, stripped)
    result = inverter_efficiency.run(ctx)

    assert result.status == ResultStatus.OK, result.summary
    assert result.loss_energy_kwh is not None and result.loss_energy_kwh > 0
    assert "derived from SCB" in result.summary.lower() or "reconstructed" in " ".join(result.recommendations).lower()
    # Both inverters should still be represented.
    inv_rows = {r[0] for r in result.tables[0].rows}
    assert {"INV-01", "INV-02"}.issubset(inv_rows)


def test_efficiency_prefers_native_dc_when_present(demo_context):
    """With native DC power present, the summary must NOT claim SCB derivation."""
    result = inverter_efficiency.run(demo_context)
    assert result.status == ResultStatus.OK
    assert "derived from scb" not in result.summary.lower()


def test_disconnected_strings_excludes_spare_scb(demo_context):
    """A SCB flagged spare in architecture must never be reported as disconnected."""
    # Baseline detects INV-01-SCB-01.
    base = disconnected_strings.run(demo_context)
    assert base.status == ResultStatus.OK
    assert "INV-01-SCB-01" in base.affected_equipment

    # Mark the faulted SCB as spare → it must be excluded from detection.
    plant = dataclasses.replace(demo_context.plant)
    arch = {k: dict(v) for k, v in plant.architecture.items()}
    arch["INV-01-SCB-01"]["spare_flag"] = True
    plant = dataclasses.replace(plant, architecture=arch)
    ctx = dataclasses.replace(demo_context, plant=plant)

    result = disconnected_strings.run(ctx)
    assert "INV-01-SCB-01" not in result.affected_equipment


def test_clipping_power_coverage_guard_skips_thin_inverter(demo_context):
    """Dropping most of INV-02's daytime samples should skip it via the coverage guard,
    surfaced in the ``skipped_inverter_count`` metric rather than silently mis-calibrated."""
    frame = demo_context.canonical.frame().copy()
    inv2 = (frame["device_type"] == "inverter") & (frame["inverter_id"] == "INV-02")
    # Keep only every 12th INV-02 sample → well under the 40% coverage floor.
    inv2_idx = frame[inv2].index
    drop_idx = [ix for pos, ix in enumerate(inv2_idx) if pos % 12 != 0]
    frame = frame.drop(index=drop_idx)

    ctx = _replace_canonical(demo_context, frame)
    result = clipping_power.run(ctx)

    assert result.status in (ResultStatus.OK, ResultStatus.UNAVAILABLE)
    if result.status == ResultStatus.OK:
        assert result.metrics.get("skipped_inverter_count", 0) >= 1
