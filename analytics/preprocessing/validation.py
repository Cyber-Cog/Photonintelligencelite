"""Validation stage: structural + data-quality checks before standardization.

Ported/extended from PIC's backend/modules/data_setup/validators.py concepts, generalized
for arbitrary uploaded CSVs (PIC's version validated against fixed internal templates;
PIC Lite validates against the *resolved mapping* instead).

Every issue is either a blocker (analysis cannot proceed) or a warning (analysis proceeds,
accuracy may be reduced) — never a silent failure. See docs/PRD.md §7.6.

Timestamp parse failures: when ≥80% of non-null rows parse successfully, the issue can be
downgraded for a "proceed with warnings / drop bad rows" recovery path (plant owners prefer
partial analysis over restart). Threshold is PROCEED_WITH_DROPS_MIN_OK_RATIO.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from analytics.preprocessing.timestamps import parse_timestamp_series, sample_unparseable_values

Severity = Literal["blocker", "warning"]

NON_NEGATIVE_CANONICAL_FIELDS = {"dc_current_a", "poa_w_m2", "ghi_w_m2", "energy_kwh"}

# Fraction of non-null timestamp cells that must parse OK before we offer "drop bad rows".
PROCEED_WITH_DROPS_MIN_OK_RATIO = 0.80
# Below this share of bad parses → warning only; at/above → blocker (unless proceed-with-drops).
DATETIME_BLOCKER_BAD_RATIO = 0.05


@dataclass
class ValidationIssue:
    code: str
    severity: Severity
    message: str
    likely_cause: str
    blocks_analysis: bool
    affected_rows: int = 0
    affected_columns: list[str] = field(default_factory=list)
    sample_values: list[str] = field(default_factory=list)
    remediation: str = ""


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    row_count: int = 0
    column_count: int = 0
    timestamp_column: str | None = None
    timestamp_parse_ok: int = 0
    timestamp_parse_fail: int = 0

    @property
    def blockers(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.blocks_analysis]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if not i.blocks_analysis]

    @property
    def has_blockers(self) -> bool:
        return len(self.blockers) > 0

    @property
    def can_proceed_with_row_drops(self) -> bool:
        """True when enough timestamps parse that dropping the rest is a sensible recovery."""
        total = self.timestamp_parse_ok + self.timestamp_parse_fail
        if total <= 0:
            return False
        if self.timestamp_parse_fail <= 0:
            return False
        return (self.timestamp_parse_ok / total) >= PROCEED_WITH_DROPS_MIN_OK_RATIO

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)


def _is_garbage_header(name: str) -> bool:
    n = (name or "").strip().lower()
    return not n or n.startswith("unnamed") or n.startswith("column_")


def validate_raw_frame(
    df: pd.DataFrame,
    timestamp_column: str,
    required_columns: list[str],
    numeric_columns: list[str],
    *,
    drop_unparseable_timestamps: bool = False,
) -> ValidationReport:
    report = ValidationReport(
        row_count=len(df),
        column_count=len(df.columns),
        timestamp_column=timestamp_column,
    )

    if df.empty:
        report.add(
            ValidationIssue(
                code="empty_file",
                severity="blocker",
                message="The uploaded file contains no data rows.",
                likely_cause="The CSV export was empty or only contained a header row.",
                blocks_analysis=True,
                remediation="Re-export the SCADA file with data rows, then upload again.",
            )
        )
        return report

    missing_required = [c for c in required_columns if c not in df.columns]
    if missing_required:
        report.add(
            ValidationIssue(
                code="missing_required_columns",
                severity="blocker",
                message=f"Required columns could not be resolved: {', '.join(missing_required)}.",
                likely_cause="Automatic detection and manual mapping did not cover every mandatory field.",
                blocks_analysis=True,
                affected_columns=missing_required,
                remediation="Go back to Setup and map the missing columns (or ignore unused ones).",
            )
        )
        return report

    if timestamp_column not in df.columns:
        report.add(
            ValidationIssue(
                code="missing_required_columns",
                severity="blocker",
                message=f"Timestamp column '{timestamp_column}' is not present in the file.",
                likely_cause="Column mapping points at a header that was lost during Excel conversion.",
                blocks_analysis=True,
                affected_columns=[timestamp_column],
                remediation="Fix column mapping: choose the real Date/Time column, then retry validation.",
            )
        )
        return report

    ts_raw = df[timestamp_column]
    if ts_raw.dtype == object or str(ts_raw.dtype) == "string":
        blank = ts_raw.isna() | ts_raw.astype(str).str.strip().isin({"", "nan", "None", "NaT", "null"})
        present = ~blank
        ts_for_parse = ts_raw.mask(blank, other=pd.NA)
    else:
        blank = ts_raw.isna()
        present = ~blank
        ts_for_parse = ts_raw

    ts_parsed = parse_timestamp_series(ts_for_parse)
    n_bad_ts = int((present & ts_parsed.isna()).sum())
    n_ok_ts = int((present & ts_parsed.notna()).sum())
    report.timestamp_parse_ok = n_ok_ts
    report.timestamp_parse_fail = n_bad_ts

    garbage_ts_col = _is_garbage_header(timestamp_column)
    samples = sample_unparseable_values(ts_for_parse, ts_parsed) if n_bad_ts > 0 else []

    if n_bad_ts > 0:
        n_present = n_ok_ts + n_bad_ts
        bad_ratio = n_bad_ts / max(n_present, 1)
        is_blocker = (bad_ratio >= DATETIME_BLOCKER_BAD_RATIO) and not drop_unparseable_timestamps

        if garbage_ts_col:
            remediation = (
                f"Column '{timestamp_column}' looks like a broken Excel header (title row / merged cells). "
                "In Setup, remap Timestamp to the real date/time column (e.g. 'Date And Time'), then retry validation. "
                "Re-upload only if the file is corrupt."
            )
            likely = (
                "Excel title rows or multi-row headers were treated as the column names, so the real "
                "'Date And Time' header was lost into an Unnamed column."
            )
        else:
            remediation = (
                f"Confirm that '{timestamp_column}' is the timestamp column. "
                "If it is, try Fix column mapping and pick a format-friendly column, or proceed by dropping "
                f"unparseable rows when ≥{int(PROCEED_WITH_DROPS_MIN_OK_RATIO * 100)}% of rows are good. "
                "Re-upload only if the export itself is corrupt."
            )
            likely = "Mixed timestamp formats, Excel serial dates, or a non-timestamp column mapped as Timestamp."

        sample_note = f" Sample raw values: {', '.join(repr(s) for s in samples)}." if samples else ""
        report.add(
            ValidationIssue(
                code="invalid_datetime_format",
                severity="blocker" if is_blocker else "warning",
                message=(
                    f"{n_bad_ts:,} of {n_present:,} value(s) in timestamp column '{timestamp_column}' "
                    f"could not be parsed ({n_ok_ts:,} OK).{sample_note}"
                ),
                likely_cause=likely,
                blocks_analysis=is_blocker,
                affected_rows=n_bad_ts,
                affected_columns=[timestamp_column],
                sample_values=samples,
                remediation=remediation,
            )
        )

    n_missing_ts = int(blank.sum())
    if n_missing_ts > 0:
        report.add(
            ValidationIssue(
                code="missing_timestamps",
                severity="warning",
                message=f"{n_missing_ts} row(s) have no timestamp and will be dropped.",
                likely_cause="Blank rows or logger gaps in the source export.",
                blocks_analysis=False,
                affected_rows=n_missing_ts,
                affected_columns=[timestamp_column],
                remediation="No action needed unless too many rows are blank — then check the export.",
            )
        )

    valid_ts = ts_parsed.dropna()
    n_duplicate_ts = int(valid_ts.duplicated().sum())
    if n_duplicate_ts > 0:
        report.add(
            ValidationIssue(
                code="duplicate_timestamps",
                severity="warning",
                message=f"{n_duplicate_ts} duplicate timestamp value(s) found.",
                likely_cause="Overlapping export windows or multiple loggers writing the same clock tick.",
                blocks_analysis=False,
                affected_rows=n_duplicate_ts,
                affected_columns=[timestamp_column],
            )
        )

    if len(valid_ts) > 1 and not valid_ts.is_monotonic_increasing:
        n_unsorted = int((valid_ts.diff().dropna() < pd.Timedelta(0)).sum())
        report.add(
            ValidationIssue(
                code="unsorted_timestamps",
                severity="warning",
                message=f"Timestamps are not in chronological order ({n_unsorted} inversion(s)).",
                likely_cause="Export was not sorted by time before being saved.",
                blocks_analysis=False,
                affected_rows=n_unsorted,
                affected_columns=[timestamp_column],
            )
        )

    for col in numeric_columns:
        if col not in df.columns:
            continue
        series = df[col]
        numeric = pd.to_numeric(series, errors="coerce")
        n_non_numeric = int(numeric.isna().sum() - series.isna().sum())
        if n_non_numeric > 0:
            report.add(
                ValidationIssue(
                    code="non_numeric_values",
                    severity="warning",
                    message=f"Column '{col}' has {n_non_numeric} non-numeric value(s); they will be treated as missing.",
                    likely_cause="Text placeholders (e.g. 'N/A', '-') mixed into a numeric column.",
                    blocks_analysis=False,
                    affected_rows=n_non_numeric,
                    affected_columns=[col],
                )
            )

        if col in NON_NEGATIVE_CANONICAL_FIELDS or col.endswith("_a") or col.endswith("_w_m2"):
            n_negative = int((numeric < 0).sum())
            if n_negative > 0:
                report.add(
                    ValidationIssue(
                        code="negative_values_where_impossible",
                        severity="warning",
                        message=f"Column '{col}' has {n_negative} negative value(s), which is physically impossible for this signal.",
                        likely_cause="Sensor fault, unit mismatch, or a sign convention change mid-export.",
                        blocks_analysis=False,
                        affected_rows=n_negative,
                        affected_columns=[col],
                    )
                )

    n_fully_null_rows = int(df[required_columns].isna().all(axis=1).sum()) if required_columns else 0
    if n_fully_null_rows > 0:
        report.add(
            ValidationIssue(
                code="corrupted_rows",
                severity="warning",
                message=f"{n_fully_null_rows} row(s) have no usable data in any required column.",
                likely_cause="Truncated export or a logger gap padded with blank rows.",
                blocks_analysis=False,
                affected_rows=n_fully_null_rows,
            )
        )

    return report
