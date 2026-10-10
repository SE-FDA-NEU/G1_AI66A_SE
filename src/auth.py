"""Password hashing, JWT handling, and authenticated-user dependencies."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import get_settings
from src.database import SessionDep
from src.errors import error_detail
from src.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a password with a random salt using scrypt."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
    )
    return "scrypt$" + _b64encode(salt) + "$" + _b64encode(derived)


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password hash without leaking comparison timing."""
    try:
        scheme, salt_value, digest_value = encoded.split("$", 2)
        if scheme != "scrypt":
            return False
        salt = _b64decode(salt_value)
        expected = _b64decode(digest_value)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(user: User, expires_in: int | None = None) -> str:
    """Create a signed JWT containing the user subject, role, and expiry."""
    if user.id is None:
        raise ValueError("Cannot issue a token for a user without an id.")
    now = int(time.time())
    lifetime = expires_in or get_settings().JWT_EXPIRATION_MINUTES * 60
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": str(user.id), "role": user.role, "iat": now, "exp": now + lifetime}
    encoded_header = _b64encode(json.dumps(header, separators=(",", ":")).encode())
    encoded_payload = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_payload}".encode()
    signature = hmac.new(
        get_settings().SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64encode(signature)}"


def decode_access_token(token: str) -> dict[str, object]:
    """Validate a JWT signature and expiry, returning its claims."""
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        signing_input = f"{encoded_header}.{encoded_payload}".encode()
        expected = hmac.new(
            get_settings().SECRET_KEY.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, _b64decode(encoded_signature)):
            raise ValueError("invalid signature")
        header = json.loads(_b64decode(encoded_header))
        payload = json.loads(_b64decode(encoded_payload))
        if header.get("alg") != "HS256" or not isinstance(payload.get("exp"), int):
            raise ValueError("invalid claims")
        if payload["exp"] <= int(time.time()):
            raise ValueError("expired token")
        if not payload.get("sub") or not payload.get("role"):
            raise ValueError("missing claims")
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("ERR_INVALID_TOKEN", "The access token is invalid or expired."),
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: SessionDep,
) -> User:
    """Resolve the bearer token to its current database user."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("ERR_AUTH_REQUIRED", "Authentication is required."),
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_access_token(credentials.credentials)
    try:
        user_id = int(str(claims["sub"]))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("ERR_INVALID_TOKEN", "The access token is invalid or expired."),
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    user = session.get(User, user_id)
    if user is None or user.role != claims.get("role"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("ERR_INVALID_TOKEN", "The access token is invalid or expired."),
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_seller(user: CurrentUser) -> User:
    """Require an authenticated seller for seller-only endpoints."""
    if user.role != "seller":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail("ERR_SELLER_REQUIRED", "A seller account is required."),
        )
    return user


SellerUser = Annotated[User, Depends(require_seller)]


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
