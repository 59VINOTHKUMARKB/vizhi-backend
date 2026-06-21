"""Frontend user authentication helpers."""

from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

import bcrypt
import httpx
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db.session import get_db
from app.models.db_models import AuthAccountRow, UserRow
from app.schemas.responses import UserResponse

_auth_header = APIKeyHeader(name="Authorization", auto_error=False)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class GoogleIdentity:
    provider_user_id: str
    email: str
    email_verified: bool
    name: str = ""
    avatar_url: str = ""


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not _EMAIL_RE.match(normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid email address",
        )
    return normalized


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def user_to_response(user: UserRow) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        email_verified=bool(user.email_verified),
        name=user.name or "",
        avatar_url=user.avatar_url or "",
    )


def create_access_token(user: UserRow) -> str:
    now = _dt.datetime.now(_dt.timezone.utc)
    exp = now + _dt.timedelta(minutes=settings.auth_token_ttl_minutes)
    payload = {
        "sub": user.id,
        "email": user.email,
        "iss": settings.auth_jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return _encode_token(payload)


async def get_current_user(
    authorization: str | None = Security(_auth_header),
    db: AsyncSession = Depends(get_db),
) -> UserRow:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    token = authorization.removeprefix("Bearer ").strip()
    payload = _decode_token(token)
    user_id = str(payload.get("sub", ""))
    result = await db.execute(select(UserRow).where(UserRow.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )
    return user


async def find_user_by_email(db: AsyncSession, email: str) -> UserRow | None:
    result = await db.execute(select(UserRow).where(UserRow.email == email))
    return result.scalar_one_or_none()


async def find_auth_account(
    db: AsyncSession,
    *,
    provider: str,
    provider_user_id: str | None = None,
    user_id: str | None = None,
) -> AuthAccountRow | None:
    stmt = select(AuthAccountRow).where(AuthAccountRow.provider == provider)
    if provider_user_id is not None:
        stmt = stmt.where(AuthAccountRow.provider_user_id == provider_user_id)
    if user_id is not None:
        stmt = stmt.where(AuthAccountRow.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    email: str,
    email_verified: bool,
    name: str = "",
    avatar_url: str = "",
) -> UserRow:
    user = UserRow(
        id=f"usr_{uuid.uuid4().hex[:12]}",
        email=email,
        email_verified=1 if email_verified else 0,
        name=name,
        avatar_url=avatar_url,
    )
    db.add(user)
    await db.flush()
    return user


async def link_password_account(
    db: AsyncSession,
    *,
    user: UserRow,
    password: str,
) -> AuthAccountRow:
    existing = await find_auth_account(db, provider="password", user_id=user.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Password login already exists for this email",
        )

    account = AuthAccountRow(
        id=f"auth_{uuid.uuid4().hex[:12]}",
        user_id=user.id,
        provider="password",
        provider_user_id=None,
        password_hash=hash_password(password),
    )
    db.add(account)
    await db.flush()
    return account


async def link_google_account(
    db: AsyncSession,
    *,
    user: UserRow,
    identity: GoogleIdentity,
) -> AuthAccountRow:
    existing = await find_auth_account(
        db,
        provider="google",
        provider_user_id=identity.provider_user_id,
    )
    if existing:
        return existing

    account = AuthAccountRow(
        id=f"auth_{uuid.uuid4().hex[:12]}",
        user_id=user.id,
        provider="google",
        provider_user_id=identity.provider_user_id,
    )
    db.add(account)
    await db.flush()
    return account


async def verify_google_id_token(id_token: str) -> GoogleIdentity:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google identity token",
        )

    data = response.json()
    audience = str(data.get("aud", ""))
    if settings.google_client_id and audience != settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token audience does not match this app",
        )

    email_verified = str(data.get("email_verified", "")).lower() == "true"
    email = normalize_email(str(data.get("email", "")))
    provider_user_id = str(data.get("sub", ""))
    if not provider_user_id or not email_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account email must be verified",
        )

    return GoogleIdentity(
        provider_user_id=provider_user_id,
        email=email,
        email_verified=email_verified,
        name=str(data.get("name", "")),
        avatar_url=str(data.get("picture", "")),
    )


def _encode_token(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join(
        [
            _b64url(json.dumps(header, separators=(",", ":")).encode()),
            _b64url(json.dumps(payload, separators=(",", ":")).encode()),
        ]
    )
    signature = hmac.new(
        settings.auth_jwt_secret.encode(),
        signing_input.encode(),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64url(signature)}"


def _decode_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise _auth_error("Invalid access token") from exc

    signing_input = f"{header_b64}.{payload_b64}"
    expected = hmac.new(
        settings.auth_jwt_secret.encode(),
        signing_input.encode(),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_b64url(expected), signature_b64):
        raise _auth_error("Invalid access token")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (json.JSONDecodeError, ValueError) as exc:
        raise _auth_error("Invalid access token") from exc

    if payload.get("iss") != settings.auth_jwt_issuer:
        raise _auth_error("Invalid access token issuer")
    if int(payload.get("exp", 0)) < int(
        _dt.datetime.now(_dt.timezone.utc).timestamp()
    ):
        raise _auth_error("Access token expired")
    return payload


def _auth_error(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}").decode()
