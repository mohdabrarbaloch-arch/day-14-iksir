"""Password hashing and JWT handling.

bcrypt for passwords (via the `bcrypt` package directly, not passlib -- passlib
has had version-pin breakage with bcrypt 4.x and this avoids that whole class of
problem). JWT is HS256 with the secret from settings.

The token carries `sub` (user id), `email`, and `role`, plus `exp` and `iat`.
Nothing sensitive goes in the payload -- it is signed, not encrypted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from .config import settings

# bcrypt truncates at 72 bytes; reject longer passwords rather than silently
# ignoring the tail, which is a real (if obscure) security footgun.
MAX_PASSWORD_BYTES = 72


class PasswordError(ValueError):
    """Raised when a password cannot be hashed for a stated reason."""


def hash_password(password: str) -> str:
    """Hash a password with bcrypt at the configured cost."""
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise PasswordError(
            f"password is {len(encoded)} bytes; bcrypt accepts at most " f"{MAX_PASSWORD_BYTES}"
        )
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(encoded, salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against a stored hash, returning False on any mismatch."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, email: str, role: str) -> str:
    """Mint a signed access token for a user."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


class TokenError(ValueError):
    """Raised when a token is missing, malformed, or expired."""


def decode_access_token(token: str) -> dict[str, object]:
    """Decode and verify a token, raising `TokenError` with a clear reason."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("token is invalid") from exc
