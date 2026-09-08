"""Access and refresh tokens (Plan.md section 4).

The access token is a short-lived signed JWT: it is checked on every
request, so verifying it must not require a database round trip.

The refresh token is not a JWT. It is opaque randomness, and only its
SHA-256 hash is stored, so a leaked database yields nothing usable. That
also makes `DELETE /api/auth/logout` mean something -- a signed token
cannot be withdrawn, but a stored row can be marked revoked.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings

_ALGORITHM = "HS256"
_ACCESS = "access"


class InvalidToken(Exception):
    """The token was missing, malformed, expired, or not an access token."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str) -> tuple[str, int]:
    """Returns the token and how many seconds it is good for."""
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not set; refusing to sign a token.")
    lifetime = timedelta(minutes=settings.access_token_minutes)
    issued = _now()
    payload = {
        "sub": str(user_id),
        "type": _ACCESS,
        "iat": issued,
        "exp": issued + lifetime,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)
    return token, int(lifetime.total_seconds())


def read_access_token(token: str) -> str:
    """The user id the token is for, or InvalidToken."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as error:
        raise InvalidToken(str(error)) from error

    # A refresh token must never be accepted where an access token belongs,
    # so the type is checked rather than assumed from the signature alone.
    if payload.get("type") != _ACCESS:
        raise InvalidToken("not an access token")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise InvalidToken("no subject")
    return subject


def new_refresh_token() -> tuple[str, str, datetime]:
    """A fresh refresh token: the secret, its hash to store, and its expiry."""
    token = secrets.token_urlsafe(48)
    expires = _now() + timedelta(days=get_settings().refresh_token_days)
    return token, hash_refresh_token(token), expires


def hash_refresh_token(token: str) -> str:
    """SHA-256 hex, which is what the refresh_tokens.token_hash column holds.

    Plain SHA-256 rather than argon2 on purpose: this is 48 bytes of
    randomness, not a guessable human password, so there is nothing for a
    slow hash to defend against and lookups stay a single indexed query.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
