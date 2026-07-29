from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.services.jwt_service import jwt_service
from app.core.limiter import limiter
from app.core.schemas import MessageResponse
from app.database import get_async_db
from app.game.services import game_service
from app.models.user import User
from app.settings import is_production
from .schemas import GameHistoryOut, PasswordChange, UserOut, UserUpdate
from .services.user_service import user_service
from .types import UserId

router = APIRouter(tags=["User"])


@router.get("/profile", response_model=UserOut)
async def get_user_profile(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(
        userId=UserId(current_user.id),
        username=str(current_user.username),
        email=str(current_user.email),
        createdAt=current_user.created_at,
    )


@router.patch("/profile", response_model=UserOut)
@limiter.limit("10/minute")
async def update_profile(
    request: Request,
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> UserOut:
    return await user_service.update_profile(db, current_user, data)


@router.post("/password", response_model=MessageResponse, status_code=200)
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    response: Response,
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> MessageResponse:
    await user_service.change_password(
        db, current_user, data.current_password, data.next_password
    )

    # The change invalidated every token issued under the old password,
    # including the caller's own. Re-issue for this session so the user who
    # made the change stays signed in while other sessions are dropped.
    secure = is_production()
    for key, token in (
        (
            "access_token",
            jwt_service.create_access_token(
                str(current_user.id), current_user.token_version
            ),
        ),
        (
            "refresh_token",
            jwt_service.create_refresh_token(
                str(current_user.id), current_user.token_version
            ),
        ),
    ):
        response.set_cookie(
            key=key, value=token, httponly=True, samesite="lax", secure=secure
        )

    return MessageResponse(message="OK")


@router.post("/deactivate", response_model=MessageResponse)
@limiter.limit("3/minute")
async def deactivate_account(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> MessageResponse:
    await user_service.deactivate_account(db, current_user)
    # No token blacklisting is needed: get_current_user rejects inactive
    # users, so the existing access/refresh tokens are already unusable.
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return MessageResponse(message="OK")


@router.get("/game-history", response_model=GameHistoryOut)
async def get_game_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    role: Literal["host", "player"] | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> GameHistoryOut:
    return await game_service.get_game_history(db, current_user, limit, offset, role)
