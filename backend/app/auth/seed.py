"""Bootstrap superadmin from env on startup."""
from __future__ import annotations

import logging
import secrets

from sqlalchemy.orm import Session

from backend.app.auth.passwords import hash_password, verify_password
from backend.app.config import Settings
from backend.app.models import User

logger = logging.getLogger("pic_lite.seed")


def seed_superadmin(db: Session, settings: Settings) -> User | None:
    """Create or repair the env-configured superadmin on every API startup.

    Idempotent: missing users are created; existing users are promoted and
    kept verified/active. When ``PIC_SUPERADMIN_PASSWORD`` is set, the hash is
    refreshed if it no longer matches so local ``.env`` credentials stay usable
    after a failed first seed or password drift.
    """
    email = (settings.pic_superadmin_email or "").strip().lower()
    if not email:
        return None

    existing = db.query(User).filter(User.email == email).first()
    password = settings.pic_superadmin_password
    if existing:
        changed = False
        if existing.role != "superadmin":
            existing.role = "superadmin"
            changed = True
        if not existing.email_verified:
            existing.email_verified = True
            changed = True
        if not existing.is_active:
            existing.is_active = True
            changed = True
        if password and not verify_password(password, existing.password_hash):
            existing.password_hash = hash_password(password)
            changed = True
            logger.info("Synced superadmin password from env for %s", email)
        if changed:
            db.add(existing)
            db.commit()
            db.refresh(existing)
            logger.info("Repaired / promoted superadmin account: %s", email)
        return existing

    if not password:
        password = secrets.token_urlsafe(16)
        logger.warning(
            "PIC_SUPERADMIN_PASSWORD not set — generated temporary password for %s: %s",
            email,
            password,
        )

    user = User(
        email=email,
        name=settings.pic_superadmin_name or "Superadmin",
        password_hash=hash_password(password),
        role="superadmin",
        email_verified=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Seeded superadmin account: %s", email)
    return user
