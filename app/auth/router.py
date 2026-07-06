from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.exceptions import (
    AccountLockedError,
    InvalidCredentialsError,
    RefreshTokenMissingError,
    RegistrationFailedError,
    TokenRevokedError,
    UsernameAlreadyExistsError,
)
from app.auth.services.auth_service import auth_service
from app.auth.services.jwt_service import jwt_service
from app.core.limiter import limiter
from app.core.schemas import MessageResponse
from app.core.security import (
    blacklist_refresh_token,
    get_login_attempts,
    is_refresh_token_blacklisted,
    MAX_LOGIN_ATTEMPTS,
    record_failed_login,
    reset_login_attempts,
)
from app.database import get_async_db
from app.settings import is_dev
from app.user.schemas import UserCreate, UserLogin, UserOut
from app.user.services.user_service import user_service

router = APIRouter(tags=["Auth"])


def _set_auth_cookies(
    response: Response, access_token: str, refresh_token: str
) -> None:
    secure = not is_dev()
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=secure,
    )


@router.post("/register", response_model=UserOut)
@limiter.limit("5/minute")
async def register(
    request: Request,
    user: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_async_db),
) -> UserOut:
    try:
        found_user = await user_service.get_user_by_email(db, user.email)
        if found_user is not None:
            raise RegistrationFailedError()

        created_user = await user_service.create_user(
            db, user.username, user.email, user.password
        )
    except UsernameAlreadyExistsError:
        raise RegistrationFailedError()

    access_token = jwt_service.create_access_token(str(created_user.id))
    refresh_token = jwt_service.create_refresh_token(str(created_user.id))
    _set_auth_cookies(response, access_token, refresh_token)
    return user_service.user_to_response(created_user)


@router.post("/login", response_model=UserOut)
@limiter.limit("5/minute")
async def login(
    request: Request,
    data: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_async_db),
) -> UserOut:
    attempts = await get_login_attempts(data.email)
    if attempts >= MAX_LOGIN_ATTEMPTS:
        raise AccountLockedError()

    try:
        user, access_token, refresh_token = await auth_service.login(
            db, data.email, data.password
        )
    except InvalidCredentialsError:
        await record_failed_login(data.email)
        raise

    await reset_login_attempts(data.email)
    _set_auth_cookies(response, access_token, refresh_token)
    return user_service.user_to_response(user)


@router.post("/refresh", response_model=MessageResponse)
@limiter.limit("30/minute")
async def refresh(
    request: Request,
    response: Response,
) -> MessageResponse:
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise RefreshTokenMissingError()

    if await is_refresh_token_blacklisted(refresh_token):
        raise TokenRevokedError()

    payload = jwt_service.verify_refresh_token(refresh_token)
    user_id = payload["sub"]

    access_token = jwt_service.create_access_token(str(user_id))
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=not is_dev(),
    )
    return MessageResponse(message="OK")


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response) -> MessageResponse:
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            await blacklist_refresh_token(
                refresh_token, jwt_service.refresh_token_lifetime
            )
        except Exception:
            pass

    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return MessageResponse(message="OK")
