from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.auth.validators import AuthValidators

from .types import UserId


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        return AuthValidators.validate_username(v)

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        return AuthValidators.validate_password(v)


class UserOut(BaseModel):
    userId: UserId
    username: str
    email: EmailStr


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, validation_alias="username")
    email: EmailStr | None = Field(default=None, validation_alias="email")

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return AuthValidators.validate_username(v)


class PasswordChange(BaseModel):
    current_password: str = Field(validation_alias="currentPassword")
    new_password: str = Field(validation_alias="newPassword")

    @field_validator("new_password")
    @classmethod
    def new_password_valid(cls, v: str) -> str:
        return AuthValidators.validate_password(v)

    model_config = {"populate_by_name": True}


class GameHistoryItem(BaseModel):
    session_id: str = Field(serialization_alias="sessionId")
    room_code: str = Field(serialization_alias="roomCode")
    quiz_id: str = Field(serialization_alias="quizId")
    quiz_title: str = Field(serialization_alias="quizTitle")
    role: Literal["host", "player"]
    score: int | None = None
    rank: int | None = None
    total_players: int = Field(serialization_alias="totalPlayers")
    started_at: datetime | None = Field(default=None, serialization_alias="startedAt")
    ended_at: datetime | None = Field(default=None, serialization_alias="endedAt")
    status: str

    model_config = {"populate_by_name": True}


class GameHistoryOut(BaseModel):
    items: list[GameHistoryItem]
    total: int

    model_config = {"populate_by_name": True}
