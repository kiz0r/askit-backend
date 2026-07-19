from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.limiter import limiter
from app.core.schemas import MessageResponse
from app.database import get_async_db
from app.game.services import game_service
from app.models.user import User
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
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> MessageResponse:
    await user_service.change_password(
        db, current_user, data.current_password, data.next_password
    )
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
