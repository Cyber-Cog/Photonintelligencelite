"""Lenient auth email type for local / lab domains.

Pydantic ``EmailStr`` (via email-validator) rejects special-use TLDs such as
``.local``, which breaks the default superadmin ``admin@pic.local``. Auth
request schemas use ``AuthEmail`` instead — shape-checked, but deliverability
and reserved-TLD rules are not applied.
"""
from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

# Practical address shape: local@domain with at least one dot in the domain.
# Allows lab TLDs (.local, .test, .invalid, .localhost, .internal, …).
_AUTH_EMAIL_RE = re.compile(
    r"^(?P<local>[a-z0-9.!#$%&'*+/=?^_`{|}~-]+)"
    r"@"
    r"(?P<domain>"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
    r")$",
    re.IGNORECASE,
)


def normalize_auth_email(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("email must be a string")
    email = value.strip().lower()
    if not email or len(email) > 320:
        raise ValueError("value is not a valid email address")
    if ".." in email or email.startswith(".") or "@." in email:
        raise ValueError("value is not a valid email address")
    match = _AUTH_EMAIL_RE.match(email)
    if not match:
        raise ValueError("value is not a valid email address")
    local = match.group("local")
    if not local or local.startswith(".") or local.endswith("."):
        raise ValueError("value is not a valid email address")
    return email


AuthEmail = Annotated[str, AfterValidator(normalize_auth_email)]
