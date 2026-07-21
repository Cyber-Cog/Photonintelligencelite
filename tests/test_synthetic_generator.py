"""Sanity checks on the synthetic data generator itself — a bug here would silently
invalidate every other algorithm test. See tests/fixtures/synthetic_generator.py.
"""
from __future__ import annotations

from tests.fixtures.synthetic_generator import generate


def test_generate_is_deterministic():
    df_a, _ = generate()
    df_b, _ = generate()
    pd_equal = df_a.equals(df_b)
    assert pd_equal


def test_generate_produces_expected_equipment_and_columns():
    df, truth = generate()
    assert "Timestamp" in df.columns
    assert "Equipment ID" in df.columns
    equipment = set(df["Equipment ID"].unique())
    assert "INV-01" in equipment
    assert "INV-01-SCB-01" in equipment
    assert "INV-01-SCB-01-STR-01" in equipment
    assert "PLANT-WMS-01" in equipment
    assert truth.disconnected_string["equipment_id"] == "INV-01-SCB-01-STR-01"


def test_generate_has_multiple_days_of_data():
    df, _ = generate()
    days = df["Timestamp"].str.slice(0, 10).nunique()
    assert days == 3
