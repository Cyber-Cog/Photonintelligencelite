"""AnalysisContext: the single object every algorithm receives.

See docs/architecture_decisions.md §1-2 for the canonical schema and context contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

CANONICAL_COLUMNS: list[str] = [
    "timestamp_utc",
    "device_id",
    "device_type",
    "inverter_id",
    "scb_id",
    "string_id",
    "ac_power_kw",
    "dc_power_kw",
    "dc_current_a",
    "dc_voltage_v",
    "poa_w_m2",
    "ghi_w_m2",
    "module_temp_c",
    "ambient_temp_c",
    "energy_kwh",
]


class CanonicalDataAccess:
    """Lazy-ish accessor over canonical data.

    Two backends:
      - in-memory: wraps a single pandas DataFrame (used for small jobs, tests, and the
        synthetic demo dataset).
      - partitioned: reads only the requested columns/partitions from
        ``{job_dir}/canonical/device_type=*/date=*/part.parquet`` so large datasets are
        never materialized in full. Column/partition pruning happens at the pandas
        ``read_parquet`` layer (pyarrow engine); this can be swapped for a Polars lazy
        scan later without changing this class's public surface.
    """

    def __init__(self, *, frame: Optional[pd.DataFrame] = None, partition_dir: Optional[Path] = None):
        if frame is None and partition_dir is None:
            raise ValueError("CanonicalDataAccess requires either `frame` or `partition_dir`")
        self._frame = frame
        self._partition_dir = partition_dir

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> "CanonicalDataAccess":
        return cls(frame=frame)

    @classmethod
    def from_partitions(cls, partition_dir: Path) -> "CanonicalDataAccess":
        return cls(partition_dir=partition_dir)

    def frame(
        self,
        columns: Optional[Iterable[str]] = None,
        device_types: Optional[Iterable[str]] = None,
    ) -> pd.DataFrame:
        cols = list(columns) if columns else None
        types = set(device_types) if device_types else None

        if self._frame is not None:
            df = self._frame
            if types:
                df = df[df["device_type"].isin(types)]
            if cols:
                keep = [c for c in cols if c in df.columns]
                df = df[keep]
            return df.copy()

        assert self._partition_dir is not None
        parts: list[pd.DataFrame] = []
        search_dirs = (
            [self._partition_dir / f"device_type={t}" for t in types]
            if types
            else list(self._partition_dir.glob("device_type=*"))
        )
        for d in search_dirs:
            if not d.exists():
                continue
            # Hive partition key lives in the folder name, not inside each parquet file.
            device_type_value = d.name.split("=", 1)[1] if "=" in d.name else None
            for f in d.rglob("*.parquet"):
                # Never request device_type from the file schema — it was stripped on write.
                read_cols = None if cols is None else [c for c in cols if c != "device_type"]
                part = pd.read_parquet(f, columns=read_cols or None)
                if device_type_value is not None:
                    part["device_type"] = device_type_value
                if cols is not None:
                    for missing in cols:
                        if missing not in part.columns:
                            part[missing] = pd.NA if missing != "device_type" else device_type_value
                    keep = [c for c in cols if c in part.columns]
                    part = part[keep]
                parts.append(part)
        if not parts:
            return pd.DataFrame(columns=cols or CANONICAL_COLUMNS)
        return pd.concat(parts, ignore_index=True)

    def columns(self) -> list[str]:
        """Schema-only column lookup (includes empty placeholder columns).

        Prefer :meth:`populated_columns` for prerequisite / readiness checks — the
        canonical schema always lists telemetry columns even when they are all-null
        for a given upload.
        """
        if self._frame is not None:
            return list(self._frame.columns)

        assert self._partition_dir is not None
        import pyarrow.parquet as pq

        for d in self._partition_dir.glob("device_type=*"):
            for f in d.rglob("*.parquet"):
                # `device_type` itself is a Hive partition column: pyarrow's partitioned
                # writer strips it from the file's own schema, so it must be added back.
                return [*pq.ParquetFile(f).schema_arrow.names, "device_type"]
        return []

    def populated_columns(self, *, batch_size: int = 8) -> set[str]:
        """Canonical fields with at least one non-null value in this job's data.

        Empty schema columns (e.g. ``dc_current_a`` when the upload has no SCB current)
        must not count as available — otherwise Validation shows \"Will run\" and Results
        later flip to \"Needs input\".
        """
        cols = [c for c in self.columns() if c]
        present: set[str] = set()
        for i in range(0, len(cols), batch_size):
            batch = cols[i : i + batch_size]
            df = self.frame(columns=batch)
            if df.empty:
                continue
            for c in df.columns:
                if df[c].notna().any():
                    present.add(c)
        return present

    def equipment_ids(self, device_type: str) -> list[str]:
        df = self.frame(columns=["device_id"], device_types=[device_type])
        return sorted(df["device_id"].dropna().unique().tolist())

    def row_count(self) -> int:
        if self._frame is not None:
            return len(self._frame)
        return len(self.frame(columns=["timestamp_utc"]))


@dataclass(frozen=True)
class PlantConfig:
    plant_name: str
    ac_capacity_mw: float
    dc_capacity_mwp: float
    module_rating_wp: float
    inverter_capacity_kw: float
    module_technology: str
    bifacial: bool
    timezone: str
    strings_per_scb: Optional[int] = None
    tariff_inr_per_kwh: Optional[float] = None
    pr_benchmark_pct: Optional[float] = None
    plant_type: str = "fixed_tilt"  # "fixed_tilt" | "tracker"
    equipment_ratings: dict[str, float] = field(default_factory=dict)
    """Per-equipment rated AC kW (inverter_id -> kW). Falls back to inverter_capacity_kw."""
    architecture: dict[str, dict] = field(default_factory=dict)
    """Per-scb architecture: scb_id -> {"inverter_id": ..., "strings_per_scb": ..., "modules_per_string": ...}"""

    @property
    def dc_capacity_kwp(self) -> float:
        return self.dc_capacity_mwp * 1000.0

    @property
    def ac_capacity_kw(self) -> float:
        return self.ac_capacity_mw * 1000.0


@dataclass(frozen=True)
class ResolvedMapping:
    """Vendor column name -> canonical field, plus per-column confidence for logging."""

    column_to_canonical: dict[str, str]
    confidence_by_column: dict[str, float]
    detected_oem_signature: Optional[str] = None


@dataclass(frozen=True)
class JobMeta:
    job_id: str
    created_at: str
    trace_id: str


@dataclass(frozen=True)
class AnalysisContext:
    """Immutable per-job context passed to every algorithm's ``run(context)``."""

    canonical: CanonicalDataAccess
    plant: PlantConfig
    mapping: ResolvedMapping
    timezone: str
    sample_interval_minutes: float
    thresholds: dict[str, dict[str, float]]
    job_meta: JobMeta

    def threshold(self, algorithm_id: str, key: str, default: float | None = None) -> float | None:
        return self.thresholds.get(algorithm_id, {}).get(key, default)

    def threshold_group(self, algorithm_id: str) -> dict[str, float]:
        return dict(self.thresholds.get(algorithm_id, {}))
