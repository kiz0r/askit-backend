from typing import Optional
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_async_db
from app.models.user import User
from app.user.services.user_service import user_service
from app.user.types import UserId
from app.auth.services.jwt_service import jwt_service
from app.auth.exceptions import (
    NotAuthenticatedError,
    UserInactiveError,
    TokenExpiredError,
    InvalidTokenError,
)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise NotAuthenticatedError()

    payload = jwt_service.verify_access_token(token)
    sub = payload.get("sub")
    if not sub:
        raise NotAuthenticatedError()

    user_id = UserId(sub)
    user = await user_service.get_user_by_id(db, user_id)

    if not user:
        raise NotAuthenticatedError()

    if not user.is_active:
        raise UserInactiveError()

    return user


async def get_optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> Optional[User]:
    """
    Get current user if authenticated, otherwise return None.

    Use for endpoints that work for both guests and logged-in users.
    """
    token = request.cookies.get("access_token")
    if not token:
        return None

    try:
        payload = jwt_service.verify_access_token(token)
        sub = payload.get("sub")
        if not sub:
            return None

        user_id = UserId(sub)
        user = await user_service.get_user_by_id(db, user_id)

        if not user or not user.is_active:
            return None

        return user
    except (TokenExpiredError, InvalidTokenError):
        return None
