"""External data clients — isolated and disabled for MVP.

Per docs/PRD.md §0 Locked Decisions, the external irradiance fallback (NASA POWER /
Global Solar Atlas) is deferred entirely out of MVP. This package exists only so the
Phase 6 implementation has an isolated home that can be enabled with a single config flag
without touching the analysis orchestrator or any core contract.

`ENABLED` must stay False until Phase 6. Nothing in analytics/core or analytics/algorithms
imports from this package.
"""

ENABLED = False
