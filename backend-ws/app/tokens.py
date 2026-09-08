"""Reading the access tokens backend-rest signs.

This service verifies, and never issues. It shares one thing with
backend-rest -- the `JWT_SECRET` and the shape of the payload -- and
nothing else: no models, no session, no call between the two. That is the
cost of checking a token without a network hop on every connection, and it
is why the constants below deliberately mirror `backend-rest`'s
`app/auth/tokens.py` rather than being imported from it. The two are
separate packages in separate environments.

Only access tokens are accepted. A refresh token is not a JWT at all, so
it cannot pass here, and the `type` claim is checked anyway rather than
inferred from the signature.
"""

from __future__ import annotations

import jwt

_ALGORITHM = "HS256"
_ACCESS = "access"


class InvalidToken(Exception):
    """The token was missing, malformed, expired, or not an access token."""


def read_access_token(token: str, secret: str) -> str:
    """The user id the token is for, or InvalidToken."""
    if not secret:
        # Refuse rather than fall through: a blank secret would make every
        # signature check meaningless, and silently captioning without
        # saving would hide the misconfiguration for as long as it lasted.
        raise InvalidToken("JWT_SECRET is not set on this service")
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as error:
        raise InvalidToken(str(error)) from error

    if payload.get("type") != _ACCESS:
        raise InvalidToken("not an access token")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise InvalidToken("no subject")
    return subject
