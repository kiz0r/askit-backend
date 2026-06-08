from datetime import datetime, timezone
from uuid import UUID

from attrs import frozen
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.exceptions import (
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UsernameAlreadyExistsError,
)
from app.auth.services.password_service import password_service
from app.models.user import User
from app.user.schemas import UserOut, UserUpdate
from app.user.types import UserId


@frozen
class UserService:
    def _to_user_id(self, value: str | UUID) -> UserId:
        if isinstance(value, UUID):
            return UserId(str(value))
        return UserId(value)

    def _from_user_id(self, user_id: UserId) -> UUID:
        return UUID(user_id)

    def user_to_response(self, user: User) -> UserOut:
        return UserOut(
            userId=self._to_user_id(user.id),
            username=user.username,
            email=user.email,
        )

    async def create_user(
        self, db: AsyncSession, username: str, email: EmailStr, password: str
    ) -> User:
        user = User(
            username=username,
            email=email,
            password_hash=password_service.hash_password(password),
        )
        try:
            db.add(user)
            await db.commit()
            await db.refresh(user)
            return user
        except IntegrityError as e:
            await db.rollback()
            error_msg = str(e.orig).lower()
            if "username" in error_msg:
                raise UsernameAlreadyExistsError()
            raise UserAlreadyExistsError()

    async def get_user_by_email(self, db: AsyncSession, email: EmailStr) -> User | None:
        result: User | None = await db.scalar(select(User).where(User.email == email))
        return result

    async def get_user_by_id(self, db: AsyncSession, user_id: UserId) -> User | None:
        return await db.get(User, self._from_user_id(user_id))

    async def update_last_login(self, db: AsyncSession, user: User) -> None:
        user.last_login = datetime.now(timezone.utc)
        await db.commit()

    async def update_profile(
        self, db: AsyncSession, user: User, data: UserUpdate
    ) -> UserOut:
        if data.username is not None:
            user.username = data.username
        try:
            await db.commit()
            await db.refresh(user)
        except IntegrityError:
            await db.rollback()
            raise UsernameAlreadyExistsError()
        return self.user_to_response(user)

    async def change_password(
        self, db: AsyncSession, user: User, current_password: str, new_password: str
    ) -> None:
        if not password_service.verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError()
        user.password_hash = password_service.hash_password(new_password)
        await db.commit()


user_service = UserService()
