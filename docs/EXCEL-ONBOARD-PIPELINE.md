# Excel onboard pipeline (production)

Phased Excel → tidy CSV path used by upload. **Measurements never go to AI.**

| Phase | Module | Role |
|-------|--------|------|
| 1 Analyzer | `excel_onboard/analyzer.py` | openpyxl metadata: sheets, merges, header depth, blanks, hidden, freeze |
| 2 Normalizer | `excel_onboard/normalizer.py` | expand merges, H/V ffill, drop blank rows/cols, numeric coerce, unicode |
| 3 Headers | `excel_onboard/header_recon.py` | multi-row → unique `ICR01_INV01_AC_POWER` names + level hints |
| 4 Metadata | `excel_onboard/metadata.py` | header/equipment payload for AI (**no data rows**) |
| 5 AI | `excel_onboard/ai_headers.py` | optional Gemini on headers only; Pydantic; retry ≤2 |
| 6 Bulk | `excel_onboard/bulk.py` | local melt via strategies / pandas; write CSV |
| 7 Faults | existing rule engine + compact AI integrity | rules first; AI not full history |
| 8 Perf | background excel finish + `skip_ai=True` | CSV complete without waiting on Gemini |
| 9 JSON | pydantic `HeaderAiResponse` | validate + retry |
| 10 Logging | structured `excel_onboard.*` logs | timings, prompt size, confidence |

Entry: `run_excel_onboard()` wired from `parse_excel_to_csv` (`run_ai=False` on convert).

NTPC ICR/INV `AC_ACTIVE_POWER_kW` + `DC_POWER` reports are covered by multi-header melt after normalize.
