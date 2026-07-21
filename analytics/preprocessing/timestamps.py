"""Robust timestamp parsing for SCADA / Excel / CSV exports.

Logic ported from PIC `backend/common/helpers.py` (`parse_timestamp` /
`normalise_timestamp`) and extended for Excel serial dates, DMY-with-seconds,
AM/PM, and pandas Series coercion. Used by validation and standardization so
both stages agree on what counts as a parseable timestamp.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd

# PIC helpers.py formats, plus common SCADA / Excel variants.
_STRING_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%y %H:%M:%S",
    "%d/%m/%y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%d %I:%M:%S %p",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
)

# Excel 1900-date system serial range roughly covering 1990–2100.
_EXCEL_SERIAL_MIN = 32874.0  # ~1990-01-01
_EXCEL_SERIAL_MAX = 73050.0  # ~2100-01-01
_EXCEL_EPOCH = datetime(1899, 12, 30)


def parse_timestamp(ts: Any) -> Optional[datetime]:
    """Parse a single timestamp value. Returns None if unparseable."""
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return None
    if isinstance(ts, pd.Timestamp):
        if pd.isna(ts):
            return None
        return ts.to_pydatetime().replace(tzinfo=None)
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None) if ts.tzinfo else ts

    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        return _from_excel_serial(float(ts))

    text = str(ts).strip()
    if not text or text.lower() in {"nan", "nat", "none", "null", ""}:
        return None

    # Numeric string that looks like an Excel serial.
    try:
        as_float = float(text)
    except ValueError:
        as_float = None
    if as_float is not None and _looks_like_excel_serial(as_float) and " " not in text and "/" not in text and "-" not in text:
        return _from_excel_serial(as_float)

    for fmt in _STRING_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            if dt.year < 2000 and dt.year >= 0:
                # Two-digit year edge from %d/%m/%y paths already expanded by strptime;
                # guard very old mis-parses only when year came through oddly.
                pass
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return dt
        except ValueError:
            continue

    # Last resort: pandas (handles ISO variants / mixed separators). Prefer dayfirst
    # for slash dates common in Indian plant exports.
    dayfirst = "/" in text or "." in text
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=dayfirst)
    if pd.isna(parsed):
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=False)
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().replace(tzinfo=None)


def normalise_timestamp(ts: Any) -> Optional[str]:
    """Parse and re-format to canonical ``YYYY-MM-DD HH:MM:SS`` (PIC helper)."""
    dt = parse_timestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def parse_timestamp_series(series: pd.Series) -> pd.Series:
    """Vectorized-friendly parse: returns datetime64[ns] with NaT for failures."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")

    # Fast path: mostly ISO / already pandas-friendly
    quick = pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=False)
    n_ok = int(quick.notna().sum())
    n_total = int(series.notna().sum())
    if n_total > 0 and n_ok / n_total >= 0.95:
        return quick

    # Day-first pass for slash-heavy columns
    dayfirst = pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=True)
    if int(dayfirst.notna().sum()) > n_ok:
        quick = dayfirst
        n_ok = int(quick.notna().sum())
        if n_total > 0 and n_ok / n_total >= 0.95:
            return quick

    # Row-wise fallback for remaining NaTs (Excel serials, odd formats)
    out = quick.copy()
    need = series.notna() & out.isna()
    if need.any():
        repaired = series.loc[need].map(parse_timestamp)
        out = out.astype("datetime64[ns]")
        out.loc[need] = pd.to_datetime(repaired, errors="coerce")
    return out


def sample_unparseable_values(series: pd.Series, parsed: pd.Series, limit: int = 5) -> list[str]:
    """Return up to ``limit`` distinct raw values that failed to parse."""
    bad_mask = series.notna() & parsed.isna()
    if not bad_mask.any():
        return []
    samples: list[str] = []
    seen: set[str] = set()
    for val in series.loc[bad_mask]:
        text = str(val).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        samples.append(text[:80])
        if len(samples) >= limit:
            break
    return samples


def _looks_like_excel_serial(value: float) -> bool:
    return _EXCEL_SERIAL_MIN <= value <= _EXCEL_SERIAL_MAX


def _from_excel_serial(value: float) -> Optional[datetime]:
    if not _looks_like_excel_serial(value):
        return None
    try:
        return _EXCEL_EPOCH + timedelta(days=float(value))
    except (OverflowError, ValueError):
        return None
