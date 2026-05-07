from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
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
        userId=UserId(str(current_user.id)),
        username=str(current_user.username),
        email=str(current_user.email),
    )


@router.patch("/profile", response_model=UserOut)
async def update_profile(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> UserOut:
    return await user_service.update_profile(db, current_user, data)


@router.post("/password", status_code=200)
async def change_password(
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, str]:
    await user_service.change_password(
        db, current_user, data.current_password, data.new_password
    )
    return {"message": "OK"}


@router.get("/game-history", response_model=GameHistoryOut)
async def get_game_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> GameHistoryOut:
    return await game_service.get_game_history(db, current_user, limit, offset)
