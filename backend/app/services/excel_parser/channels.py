"""Repeating channel-label patterns for SCADA multi-row / wide exports.

Structural signals only — not OEM product names. Used after header stitching so
``I1``..``I24`` under a current group become ``string_current_channel`` columns.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Ordered: more specific first. Group 1 = channel index when present.
_CHANNEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("string_current_channel", re.compile(r"^i\s*(\d{1,3})$", re.IGNORECASE)),
    ("string_current_channel", re.compile(r"^str(?:ing)?\s*[_\-\s]*(\d{1,3})$", re.IGNORECASE)),
    ("string_current_channel", re.compile(r"^ch(?:annel)?\s*[_\-\s]*(\d{1,3})$", re.IGNORECASE)),
    ("mppt_channel", re.compile(r"^mppt\s*[_\-\s]*(\d{1,3})$", re.IGNORECASE)),
    ("scb_channel", re.compile(r"^scb\s*[_\-\s]*(\d{1,3})$", re.IGNORECASE)),
    ("smb_channel", re.compile(r"^smb\s*[_\-\s]*(\d{1,3})$", re.IGNORECASE)),
    # Trailing forms: "String Current 12", "IDC_03"
    ("string_current_channel", re.compile(
        r"^(?:string|str)\s*(?:current|idc|i)?\s*[_\-\s]*(\d{1,3})$", re.IGNORECASE
    )),
    ("string_current_channel", re.compile(r"^idc\s*[_\-\s]*(\d{1,3})$", re.IGNORECASE)),
)

# Group labels that indicate the sub-row is per-string current channels.
_STRING_CURRENT_GROUP_RE = re.compile(
    r"string\s*currents?|strings?\s*currents?|str\s*currents?|"
    r"channel\s*currents?|string\s*i\b|idc\s*channels?",
    re.IGNORECASE,
)
_CURRENT_GROUP_RE = re.compile(r"\bcurrents?\b|\bidc\b|\bamps?\b", re.IGNORECASE)


@dataclass(frozen=True)
class ChannelMatch:
    field_type: str
    channel_index: int
    matched: str


def normalize_channel_label(value: str) -> str:
    s = (value or "").strip()
    s = re.sub(r"[\(\)\[\]{}]", " ", s)
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def match_channel_label(leaf: str) -> ChannelMatch | None:
    """Match a leaf/sub-header like ``I12``, ``STR-03``, ``CH7``."""
    n = normalize_channel_label(leaf)
    if not n:
        return None
    for field_type, pat in _CHANNEL_PATTERNS:
        m = pat.match(n)
        if m:
            return ChannelMatch(field_type=field_type, channel_index=int(m.group(1)), matched=n)
    return None


def group_suggests_string_currents(group: str) -> bool:
    g = normalize_channel_label(group)
    if not g:
        return False
    if _STRING_CURRENT_GROUP_RE.search(g):
        return True
    # Generic "… Current (A)" over I1..In still counts when leaf is a channel.
    return bool(_CURRENT_GROUP_RE.search(g) and ("string" in g or "str" in g or "channel" in g))


def classify_stitched_column(
    *,
    group: str,
    leaf: str,
    sibling_leaves: list[str] | None = None,
) -> ChannelMatch | None:
    """Classify a stitched (group, leaf) pair as a repeating channel column.

    When the group label indicates string currents, short leaves like ``I1`` are
    tagged even if the group alone would not map through the synonym table.
    Also promotes channel leaves when many siblings share the same pattern
    (e.g. I1..I24 under a blank or generic group).
    """
    leaf_match = match_channel_label(leaf)
    if leaf_match is None:
        return None

    if group_suggests_string_currents(group):
        # Force string_current_channel when group is clearly string currents,
        # even if leaf pattern said mppt/scb.
        if leaf_match.field_type in {"string_current_channel", "mppt_channel", "scb_channel", "smb_channel"}:
            return ChannelMatch(
                field_type="string_current_channel",
                channel_index=leaf_match.channel_index,
                matched=leaf_match.matched,
            )
        return leaf_match

    if leaf_match.field_type == "string_current_channel":
        # Sibling reinforcement: ≥3 I\d+ / Str\d+ leaves → treat as string channels.
        siblings = sibling_leaves or []
        channelish = sum(1 for s in siblings if match_channel_label(s) is not None)
        if channelish >= 3 or group_suggests_string_currents(group) or _CURRENT_GROUP_RE.search(
            normalize_channel_label(group)
        ):
            return leaf_match
        # Bare I1 with no useful group and few siblings — still accept I\d+ alone
        # when the leaf is unambiguously ``I`` + digits (common OEM export).
        if re.fullmatch(r"i\s*\d{1,3}", normalize_channel_label(leaf), re.IGNORECASE):
            return leaf_match

    return leaf_match


def equipment_id_for_channel(
    parent_id: str | None,
    channel_index: int,
    *,
    field_type: str = "string_current_channel",
) -> str:
    """Build a tidy Equipment ID for a melted channel column."""
    parent = (parent_id or "").strip() or "SMB-01"
    # Normalize sheet-ish names: SMB_1 / smb1 → SMB-01
    parent = _normalize_parent_id(parent)
    if field_type == "mppt_channel":
        return f"{parent}-MPPT-{channel_index:02d}"
    if field_type in {"scb_channel", "smb_channel"}:
        return f"{parent}-{channel_index:02d}" if not re.search(r"\d+$", parent) else parent
    return f"{parent}-STR-{channel_index:02d}"


def _normalize_parent_id(raw: str) -> str:
    s = raw.strip()
    m = re.match(r"^(smb|scb|inv|inverter)[_\-\s]*(\d+)$", s, re.IGNORECASE)
    if m:
        prefix = m.group(1).upper()
        if prefix == "INVERTER":
            prefix = "INV"
        return f"{prefix}-{int(m.group(2)):02d}"
    return s
