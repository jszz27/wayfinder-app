"""Who is making this request, if anyone.

Two dependencies, because the product needs both. Captioning and guide
mode work with no account at all, so most routes take `CurrentUserOrNone`;
anything that reads or writes stored history takes `CurrentUser` and
refuses without a valid token.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import InvalidToken, read_access_token
from app.db.models import User
from app.db.session import get_db

_UNAUTHENTICATED = "Sign in to do that."


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def current_user_or_none(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """The signed-in user, or None. A bad token is treated as no token."""
    token = _bearer(authorization)
    if token is None:
        return None
    try:
        subject = read_access_token(token)
        user_id = uuid.UUID(subject)
    except (InvalidToken, ValueError):
        return None
    return await db.get(User, user_id)


async def current_user(
    user: Annotated[User | None, Depends(current_user_or_none)],
) -> User:
    """The signed-in user, or 401."""
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            _UNAUTHENTICATED,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(current_user)]
CurrentUserOrNone = Annotated[User | None, Depends(current_user_or_none)]
Db = Annotated[AsyncSession, Depends(get_db)]
