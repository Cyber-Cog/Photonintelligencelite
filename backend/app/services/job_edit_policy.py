"""Job state guards for replace-upload and setup edits."""
from __future__ import annotations

from analytics.core.job_states import JobState

BLOCKED_WHILE_RUNNING = {
    JobState.QUEUED.value,
    JobState.RUNNING.value,
    JobState.GENERATING_CHARTS.value,
    JobState.GENERATING_REPORT.value,
}

REPLACEABLE_STATES = {
    JobState.UPLOADED.value,
    JobState.PARSING.value,
    JobState.MAPPING.value,
    JobState.VALIDATING.value,
    JobState.NORMALIZING.value,
    JobState.FAILED.value,
    JobState.COMPLETED.value,
    JobState.CLEANED_UP.value,
}


def can_replace_upload(state: str) -> bool:
    return state not in BLOCKED_WHILE_RUNNING and state in REPLACEABLE_STATES
