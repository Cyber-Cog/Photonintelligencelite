"""Optional SMTP delivery; falls back to logging verification links in DEV."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from backend.app.config import Settings

logger = logging.getLogger("pic_lite.email")

# Last verification / reset link emitted when SMTP is unset — useful for local DEV + OpenAPI notes.
_LAST_DEV_LINK: str | None = None


def get_last_dev_link() -> str | None:
    return _LAST_DEV_LINK


def smtp_configured(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def send_email(settings: Settings, *, to: str, subject: str, body: str) -> bool:
    """Send email via SMTP when configured. Returns True if sent."""
    global _LAST_DEV_LINK
    if "http://" in body or "https://" in body:
        for line in body.splitlines():
            if "http://" in line or "https://" in line:
                _LAST_DEV_LINK = line.strip()
                break

    if not smtp_configured(settings):
        logger.info("SMTP not configured — email to %s | %s\n%s", to, subject, body)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        logger.info("Sent email to %s (%s)", to, subject)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send email to %s", to)
        return False


def send_verification_email(settings: Settings, *, to: str, token: str) -> str:
    link = f"{settings.public_app_url.rstrip('/')}/verify-email?token={token}"
    body = (
        "Welcome to Photon Intelligence Center Lite.\n\n"
        f"Verify your email by opening this link:\n{link}\n\n"
        "If you did not sign up, ignore this message.\n"
    )
    send_email(settings, to=to, subject="Verify your PIC Lite account", body=body)
    return link


def send_password_reset_email(settings: Settings, *, to: str, token: str) -> str:
    link = f"{settings.public_app_url.rstrip('/')}/reset-password?token={token}"
    body = (
        "You requested a password reset for Photon Intelligence Center Lite.\n\n"
        f"Reset your password:\n{link}\n\n"
        "If you did not request this, ignore this message.\n"
    )
    send_email(settings, to=to, subject="Reset your PIC Lite password", body=body)
    return link
