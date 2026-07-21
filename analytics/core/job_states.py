"""Job lifecycle states shared by the backend and the analytics orchestrator.

See docs/architecture_decisions.md §7 for the full lifecycle diagram.
"""
from __future__ import annotations

from enum import Enum


class JobState(str, Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    MAPPING = "mapping"
    VALIDATING = "validating"
    NORMALIZING = "normalizing"
    QUEUED = "queued"
    RUNNING = "running"
    GENERATING_CHARTS = "generating_charts"
    GENERATING_REPORT = "generating_report"
    COMPLETED = "completed"
    FAILED = "failed"
    CLEANED_UP = "cleaned_up"

    @property
    def is_terminal(self) -> bool:
        return self in (JobState.COMPLETED, JobState.FAILED, JobState.CLEANED_UP)

    @property
    def is_active(self) -> bool:
        """States during which the frontend should keep polling."""
        return self in (
            JobState.UPLOADED,
            JobState.PARSING,
            JobState.MAPPING,
            JobState.VALIDATING,
            JobState.NORMALIZING,
            JobState.QUEUED,
            JobState.RUNNING,
            JobState.GENERATING_CHARTS,
            JobState.GENERATING_REPORT,
        )


# Ordered for progress-bar rendering on the frontend.
JOB_STATE_ORDER: list[JobState] = [
    JobState.UPLOADED,
    JobState.PARSING,
    JobState.MAPPING,
    JobState.VALIDATING,
    JobState.NORMALIZING,
    JobState.QUEUED,
    JobState.RUNNING,
    JobState.GENERATING_CHARTS,
    JobState.GENERATING_REPORT,
    JobState.COMPLETED,
]
