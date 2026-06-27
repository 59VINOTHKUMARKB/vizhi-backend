"""Frontend user authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.user_auth import (
    clear_session_cookie,
    create_access_token,
    create_user,
    find_auth_account,
    find_user_by_email,
    get_current_user,
    link_google_account,
    link_password_account,
    normalize_email,
    set_session_cookie,
    user_to_response,
    verify_google_id_token,
    verify_password,
)
from app.db.session import get_db
from app.models.db_models import UserRow
from app.schemas.requests import GoogleLoginRequest, LoginRequest, SignupRequest
from app.schemas.responses import AuthResponse, UserResponse

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    email = normalize_email(body.email)
    user = await find_user_by_email(db, email)
    if user is None:
        user = await create_user(
            db,
            email=email,
            email_verified=False,
            name=body.name.strip(),
        )

    await link_password_account(db, user=user, password=body.password)
    return _auth_response(response, user)


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    email = normalize_email(body.email)
    user = await find_user_by_email(db, email)
    if not user:
        raise _invalid_login()

    password_account = await find_auth_account(
        db,
        provider="password",
        user_id=user.id,
    )
    if (
        not password_account
        or not password_account.password_hash
        or not verify_password(body.password, password_account.password_hash)
    ):
        raise _invalid_login()

    return _auth_response(response, user)


@router.post("/google")
async def google_login(
    body: GoogleLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    identity = await verify_google_id_token(body.id_token)
    google_account = await find_auth_account(
        db,
        provider="google",
        provider_user_id=identity.provider_user_id,
    )
    if google_account:
        user = await db.get(UserRow, google_account.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Linked Google account no longer exists",
            )
        return _auth_response(response, user)

    user = await find_user_by_email(db, identity.email)
    if user is None:
        user = await create_user(
            db,
            email=identity.email,
            email_verified=identity.email_verified,
            name=identity.name,
            avatar_url=identity.avatar_url,
        )
    else:
        user.email_verified = 1
        if identity.name and not user.name:
            user.name = identity.name
        if identity.avatar_url and not user.avatar_url:
            user.avatar_url = identity.avatar_url

    await link_google_account(db, user=user, identity=identity)
    return _auth_response(response, user)


@router.get("/me")
async def me(user: UserRow = Depends(get_current_user)) -> UserResponse:
    return user_to_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    clear_session_cookie(response)


def _auth_response(response: Response, user: UserRow) -> AuthResponse:
    set_session_cookie(response, create_access_token(user))
    return AuthResponse(user=user_to_response(user))


def _invalid_login() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
    )
