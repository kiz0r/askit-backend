from typing import Tuple
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from attrs import frozen
from .jwt_service import jwt_service
from .password_service import password_service
from app.user.services.user_service import user_service
from app.models.user import User
from app.auth.exceptions import InvalidCredentialsError, UserInactiveError


@frozen
class AuthService:
    """
    Service for authentication operations.
    Orchestrates user, password, and JWT services.
    """

    async def login(
        self, db: AsyncSession, email: EmailStr, password: str
    ) -> Tuple[User, str, str]:
        user = await user_service.get_user_by_email(db, email)

        if user is None or not password_service.verify_password(
            password, user.password_hash
        ):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise UserInactiveError()

        # Update last login timestamp
        await user_service.update_last_login(db, user)

        access_token = jwt_service.create_access_token(str(user.id), user.token_version)
        refresh_token = jwt_service.create_refresh_token(
            str(user.id), user.token_version
        )

        return user, access_token, refresh_token


# Singleton instance
auth_service = AuthService()
