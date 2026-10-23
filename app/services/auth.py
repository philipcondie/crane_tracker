"""Provisioned admin accounts and revocable, opaque bearer sessions."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.base import AdminToken, AdminUser


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = _password_digest(password, salt)
    return f"scrypt${salt}${digest}"


def _password_digest(password: str, salt: str) -> str:
    return hashlib.scrypt(
        password.encode(),
        salt=bytes.fromhex(salt),
        n=2**17,
        r=8,
        p=1,
        maxmem=256 * 1024 * 1024,
    ).hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt, expected = stored.split("$")
        if algorithm != "scrypt":
            return False
        actual = _password_digest(password, salt)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# Do the same expensive password check for unknown usernames.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sign_in(session: Session, *, username: str, password: str) -> str | None:
    user = session.scalar(select(AdminUser).where(AdminUser.username == username))
    valid = verify_password(
        password, user.password_hash if user else DUMMY_PASSWORD_HASH
    )
    if not valid or user is None or not user.is_active:
        return None
    now = datetime.now(UTC)
    session.execute(delete(AdminToken).where(AdminToken.expires_at <= now))
    token = secrets.token_urlsafe(32)
    session.add(
        AdminToken(
            token_hash=token_hash(token),
            user_id=user.id,
            expires_at=now + timedelta(seconds=get_settings().admin_token_ttl_seconds),
        )
    )
    session.flush()
    return token


def get_admin(session: Session, token: str) -> AdminUser | None:
    return session.scalar(
        select(AdminUser)
        .join(AdminToken, AdminToken.user_id == AdminUser.id)
        .where(
            AdminToken.token_hash == token_hash(token),
            AdminToken.expires_at > datetime.now(UTC),
            AdminUser.is_active.is_(True),
        )
    )


def sign_out(session: Session, token: str) -> None:
    session.execute(
        delete(AdminToken).where(AdminToken.token_hash == token_hash(token))
    )
