
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from app.config import settings


def hash_password(password: str) -> str:
    """Hash a password before storing it in the database."""
    if not password:
        raise ValueError("Password cannot be empty.")

    # bcrypt supports passwords up to 72 bytes.
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must not exceed 72 UTF-8 bytes.")

    salt = bcrypt.gensalt(rounds=12)
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        salt,
    )

    return password_hash.decode("utf-8")


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """Check a supplied password against its stored hash."""
    if not plain_password or not hashed_password:
        return False

    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError, UnicodeError):
        return False


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT with an expiration timestamp."""
    if not settings.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is missing. Configure it before generating tokens."
        )

    payload = data.copy()
    now = datetime.now(timezone.utc)

    expiry = expires_delta or timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    if expiry.total_seconds() <= 0:
        raise ValueError("Token expiry must be in the future.")

    payload["iat"] = now
    payload["exp"] = now + expiry

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_access_token(token: str) -> Optional[dict]:
    """Validate a JWT and return its payload, or None if invalid."""
    if not token or not settings.SECRET_KEY:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={
                "require": ["exp", "sub"],
            },
        )

        # The application identifies users using numeric database IDs.
        if not str(payload.get("sub", "")).isdigit():
            return None

        return payload

    except (jwt.PyJWTError, ValueError, TypeError):
        return None
