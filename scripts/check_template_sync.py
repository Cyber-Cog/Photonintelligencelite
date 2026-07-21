"""Guard against SCADA format drift between pack, demo, docs, and tidy Excel output.

Run from repo root:
  .venv\\Scripts\\python.exe scripts/check_template_sync.py

Exit 0 = synced; non-zero = print mismatches (CI / pre-release check).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.common.complete_analysis_pack import (  # noqa: E402
    OFFICIAL_COLUMN_TO_CANONICAL,
    SCADA_COLUMNS,
    build_scada_csv_text,
)
from backend.app.services.excel_parser.headers import TIDY_FIELDS  # noqa: E402


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}")


def main() -> int:
    errors = 0

    if tuple(OFFICIAL_COLUMN_TO_CANONICAL.keys()) != SCADA_COLUMNS:
        _fail("OFFICIAL_COLUMN_TO_CANONICAL keys != SCADA_COLUMNS")
        errors += 1

    pack_header = build_scada_csv_text().splitlines()[0]
    expected = ",".join(SCADA_COLUMNS)
    if pack_header != expected:
        _fail(f"pack CSV header mismatch:\n  got:  {pack_header}\n  want: {expected}")
        errors += 1

    demo_path = ROOT / "tests" / "fixtures" / "demo_plant_scada.csv"
    if not demo_path.exists():
        _fail(f"demo CSV missing: {demo_path}")
        errors += 1
    else:
        with demo_path.open(newline="", encoding="utf-8") as f:
            demo_header = next(csv.reader(f))
        if demo_header != list(SCADA_COLUMNS):
            _fail(f"demo CSV header != SCADA_COLUMNS:\n  got:  {demo_header}\n  want: {list(SCADA_COLUMNS)}")
            errors += 1

    if list(TIDY_FIELDS) != list(SCADA_COLUMNS):
        _fail(f"TIDY_FIELDS != SCADA_COLUMNS:\n  got:  {list(TIDY_FIELDS)}\n  want: {list(SCADA_COLUMNS)}")
        errors += 1

    # Docs must mention each official header (lightweight drift check).
    docs = (ROOT / "docs" / "COMPLETE_DATA_FORMAT.md").read_text(encoding="utf-8")
    for col in SCADA_COLUMNS:
        if f"`{col}`" not in docs:
            _fail(f"docs/COMPLETE_DATA_FORMAT.md missing backtick mention of `{col}`")
            errors += 1

    # Aliases must resolve every official header to the documented canonical field.
    from analytics.common.aliasing import score_column

    for col, field in OFFICIAL_COLUMN_TO_CANONICAL.items():
        hit = score_column(col)
        if hit.canonical_field != field:
            _fail(f"alias score {col!r} -> {hit.canonical_field!r} (want {field!r})")
            errors += 1

    # Report builder public names used by job_service must exist.
    from analytics.reports.excel_builder import build_excel_report
    from analytics.reports.pdf_builder import build_pdf_report

    if not callable(build_excel_report) or not callable(build_pdf_report):
        _fail("build_excel_report / build_pdf_report not callable")
        errors += 1

    if errors:
        print(f"\n{errors} sync check(s) failed.")
        return 1
    print("OK: Complete Analysis Pack, demo CSV, TIDY_FIELDS, docs, aliases, and report builders are synced.")
    print(f"Canonical headers ({len(SCADA_COLUMNS)}): {', '.join(SCADA_COLUMNS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
