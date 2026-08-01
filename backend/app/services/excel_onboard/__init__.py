"""Production-grade Excel onboarding pipeline (phased).

Phases
------
1. WorkbookAnalyzer — metadata only (no AI)
2. Normalizer — merges, ffill, blank drop, numeric coerce
3. HeaderReconstruction — multi-row → unique hierarchical names
4. DataExtraction — header/equipment metadata for AI (no measurements)
5. AI — header-only Gemini assist (optional, never blocks bulk parse)
6. BulkData — local pandas / strategy melt of measurements
7–10. Fault context / performance / pydantic / logging live in callers + this package

Public entry: ``run_excel_onboard`` → CSV path + reports.
"""
from __future__ import annotations

from backend.app.services.excel_onboard.pipeline import OnboardResult, run_excel_onboard

__all__ = ["OnboardResult", "run_excel_onboard"]
