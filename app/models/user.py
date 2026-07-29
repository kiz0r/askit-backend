import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import VARCHAR, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.quiz import Quiz


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    username: Mapped[str] = mapped_column(VARCHAR(50), unique=True)
    email: Mapped[str] = mapped_column(VARCHAR(100), unique=True)
    password_hash: Mapped[str] = mapped_column(VARCHAR(250))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(default=True)
    # Bumped whenever every previously issued token must stop working, such as
    # after a password change or a deactivation. Tokens carry the value they
    # were minted with and are rejected once it falls behind.
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    quizzes: Mapped[list["Quiz"]] = relationship("Quiz", back_populates="creator")
    favorite_quizzes: Mapped[list["Quiz"]] = relationship(
        "Quiz", secondary="quiz_favorites", back_populates="favorited_by"
    )
