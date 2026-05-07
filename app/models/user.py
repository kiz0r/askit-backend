"""User-related database models."""

import uuid

from sqlalchemy import UUID, VARCHAR, Boolean, Column, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    """Registered user model."""

    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    username = Column(VARCHAR(50), unique=True, nullable=False)
    email = Column(VARCHAR(100), unique=True, nullable=False)
    password_hash = Column(VARCHAR(250), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    quizzes = relationship("Quiz", back_populates="creator")
    favorite_quizzes = relationship(
        "Quiz", secondary="quiz_favorites", back_populates="favorited_by"
    )


class AnonymousUser(Base):
    """Anonymous user for game participation without registration."""

    __tablename__ = "anonymous_users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    nickname = Column(VARCHAR(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
