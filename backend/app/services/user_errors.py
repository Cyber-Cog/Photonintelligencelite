"""Map exceptions to short, allowlisted messages for the UI.

Never surface ``[Errno 2]``, absolute server paths, or raw Python exceptions
to the frontend. Full details stay in server logs.
"""
from __future__ import annotations

import logging
import re
from pathlib import PurePosixPath, PureWindowsPath

logger = logging.getLogger("pic_lite.user_errors")

MSG_MISSING_RAW_UPLOAD = (
    "Uploaded file is no longer available. Please re-upload the SCADA file and try again."
)
MSG_VALIDATE_FAILED = (
    "Could not validate mapped data. Check your mapping and plant details, then try again."
)
MSG_PROCESS_FAILED = "This job could not be completed. Please try again or re-upload your file."
MSG_GENERIC = "Something went wrong. Please try again."

# Exact messages already written for end users (pass through unchanged).
_SAFE_EXACT: frozenset[str] = frozenset(
    {
        MSG_MISSING_RAW_UPLOAD,
        MSG_VALIDATE_FAILED,
        MSG_PROCESS_FAILED,
        MSG_GENERIC,
        "A timestamp column must be mapped before analysis can proceed.",
        "Mapping and plant config are required before validation.",
        "Mapping and plant config are required.",
        "Warnings must be acknowledged to proceed.",
        "Uploaded file is empty.",
        "Upload an .xlsx architecture file (download the template first).",
        "Provide at least one inverter_id (or generate IDs first).",
        "Provide at least one equipment ID and one signal.",
        "Cannot append files after analysis has started or finished. Start a new job.",
        "Accepted formats: .csv, .csv.gz, .xlsx, .xlsm, .xls.",
        "Uploaded file not found for this job.",
        "Uploaded file not found for this job. Please upload again.",
        "Upload parsing failed. Please upload again.",
        "This job exceeded the maximum processing time and was stopped automatically.",
        "Demo preparation failed. Please try again.",
        "Analysis is running. Wait for it to finish, then edit mapping or plant details.",
    }
)

_SAFE_PREFIXES: tuple[str, ...] = (
    "Plant configuration is incomplete",
    "Upload exceeds the ",
    "Decompressed upload exceeds the ",
    "Compressed file expands far beyond",
    "Additional file not accepted:",
    "Cannot drop unparseable rows:",
    "Cannot proceed with row drops:",
    "Job is in state ",
    "Validation still has blockers",
    "Cannot replace upload",
    "Analysis is still running",
    "Applied pattern:",
)

_UNSAFE_MARKERS = re.compile(
    r"(?:"
    r"\[Errno\s*\d+\]"
    r"|FileNotFoundError"
    r"|PermissionError"
    r"|OSError"
    r"|Traceback \(most recent call last\)"
    r"|pic-lite-jobs"
    r"|/(?:tmp|var|home|opt|usr|Users)/"
    r"|[A-Za-z]:\\"
    r"|\\\\"
    r")",
    re.IGNORECASE,
)

_EXCEPTION_TYPE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)\b")


class MissingRawUploadError(Exception):
    """Job row exists but ``raw/input.csv`` is gone (ephemeral disk / cleanup)."""

    def __init__(self, message: str = MSG_MISSING_RAW_UPLOAD) -> None:
        super().__init__(message)


def looks_like_missing_file(text: str) -> bool:
    lower = text.lower()
    if "[errno 2]" in lower or "no such file or directory" in lower:
        return True
    if "filenotfounderror" in lower:
        return True
    if "input.csv" in lower and ("not found" in lower or "no such" in lower):
        return True
    return False


def looks_unsafe_for_ui(text: str) -> bool:
    if not text or not text.strip():
        return True
    if _UNSAFE_MARKERS.search(text):
        return True
    # Absolute-looking paths that are not already caught
    for part in re.split(r"[\s'\"]+", text):
        if not part or len(part) < 4:
            continue
        if "/" in part or "\\" in part:
            try:
                posix = PurePosixPath(part.strip(":',)"))
                win = PureWindowsPath(part.strip(":',)"))
                if posix.is_absolute() or win.is_absolute():
                    return True
            except Exception:  # noqa: BLE001
                continue
    return False


def user_facing_message(
    exc: BaseException | str,
    *,
    fallback: str = MSG_GENERIC,
) -> str:
    """Return a short UI-safe string; never leak paths or errno details."""
    if isinstance(exc, MissingRawUploadError):
        return str(exc) or MSG_MISSING_RAW_UPLOAD
    if isinstance(exc, FileNotFoundError):
        return MSG_MISSING_RAW_UPLOAD
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 2:
        return MSG_MISSING_RAW_UPLOAD

    text = (exc if isinstance(exc, str) else str(exc)).strip()
    if looks_like_missing_file(text):
        return MSG_MISSING_RAW_UPLOAD
    if text in _SAFE_EXACT:
        return text
    if any(text.startswith(prefix) for prefix in _SAFE_PREFIXES):
        return text
    if looks_unsafe_for_ui(text) or _EXCEPTION_TYPE.search(text):
        logger.debug("sanitized unsafe user error → fallback (%s)", text[:120])
        return fallback

    # Only pass through short messages from intentional user-facing exceptions
    # (ValueError / HTTP-style). Other exception types stay on the server log.
    if isinstance(exc, BaseException) and not isinstance(exc, (ValueError, TypeError)):
        logger.debug("sanitized non-ValueError → fallback (%s: %s)", type(exc).__name__, text[:120])
        return fallback

    if len(text) <= 280:
        return text
    return fallback
