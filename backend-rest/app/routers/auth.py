"""Authentication endpoints (Plan.md section 4).

An account is optional in this product: captioning and guide mode work
without one, and signing in is what turns on saving and history. So these
routes exist to let someone opt in, not to guard the front door.

Tokens travel in the JSON body rather than in a cookie. That keeps the
widget's requests plain and avoids CSRF handling, at the cost of the
refresh token being reachable from JavaScript; moving it to an httpOnly
cookie is the obvious hardening if this ever leaves a portfolio.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.auth.dependencies import CurrentUser, Db
from app.auth.passwords import hash_password, needs_rehash, verify_password
from app.auth.tokens import create_access_token, hash_refresh_token, new_refresh_token
from app.db.models import RefreshToken, User

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Long enough to matter, short enough not to lecture.
MIN_PASSWORD_LENGTH = 10

_BAD_CREDENTIALS = "That email and password do not match an account."


# --- bodies -----------------------------------------------------------


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)
    display_name: str = Field(min_length=1, max_length=80)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# --- helpers ----------------------------------------------------------


def _normalise(email: str) -> str:
    """Stored lower-cased so the unique index is a real guarantee."""
    return email.strip().lower()


async def _issue(db: Db, user: User) -> TokenResponse:
    access, expires_in = create_access_token(str(user.id))
    secret, token_hash, expires_at = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    return TokenResponse(
        access_token=access, refresh_token=secret, expires_in=expires_in
    )


async def _live_refresh_token(db: Db, secret: str) -> RefreshToken:
    """The stored row for this secret, if it is still usable."""
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(secret))
    )
    if row is None or row.revoked_at is not None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "That session has ended. Sign in again."
        )
    if row.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "That session has expired. Sign in again."
        )
    return row


# --- endpoints --------------------------------------------------------


@router.post(
    "/signup", status_code=status.HTTP_201_CREATED, response_model=TokenResponse
)
async def signup(db: Db, payload: SignupRequest) -> TokenResponse:
    """Create an account and sign straight in."""
    email = _normalise(payload.email)
    if await db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "There is already an account with that email."
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
    )
    db.add(user)
    await db.flush()
    return await _issue(db, user)


@router.post("/login", response_model=TokenResponse)
async def login(db: Db, payload: LoginRequest) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == _normalise(payload.email)))

    # The same answer either way, so this cannot be used to find out which
    # email addresses have accounts.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_CREDENTIALS)

    # Signing in is the one moment the plaintext is in hand, so it is the
    # only chance to move an old hash up to current cost parameters.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    return await _issue(db, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(db: Db, payload: RefreshRequest) -> TokenResponse:
    """Trade a refresh token for a new pair, retiring the old one.

    Rotating rather than reusing means a stolen token is good for one use
    at most, and the theft shows up as a rejected refresh.
    """
    row = await _live_refresh_token(db, payload.refresh_token)
    user = await db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_CREDENTIALS)

    row.revoked_at = datetime.now(timezone.utc)
    return await _issue(db, user)


@router.delete("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(db: Db, user: CurrentUser, payload: RefreshRequest) -> None:
    """Revoke one refresh token.

    The access token is not revoked, because a signed token cannot be; it
    simply expires. That is why access tokens are short-lived.
    """
    row = await db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(payload.refresh_token)
        )
    )
    # Someone else's token is not this caller's to retire, and saying so
    # would confirm it exists. Logging out is idempotent either way.
    if row is not None and row.user_id == user.id and row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
