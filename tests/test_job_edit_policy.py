"""Tests for job edit policy (replace-upload on cleaned_up jobs)."""
from __future__ import annotations

from analytics.core.job_states import JobState
from backend.app.services.job_edit_policy import BLOCKED_WHILE_RUNNING, REPLACEABLE_STATES, can_replace_upload


def test_cleaned_up_is_not_treated_as_running():
    assert JobState.CLEANED_UP.value not in BLOCKED_WHILE_RUNNING


def test_cleaned_up_allows_replace_upload():
    assert JobState.CLEANED_UP.value in REPLACEABLE_STATES
    assert can_replace_upload(JobState.CLEANED_UP.value) is True


def test_running_blocks_replace():
    assert can_replace_upload(JobState.RUNNING.value) is False
