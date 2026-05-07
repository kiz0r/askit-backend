"""Quiz-related database models."""

import uuid

from sqlalchemy import (
    UUID,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Table,
    VARCHAR,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.quiz.schemas import QuizStatus, QuizVisibility


# Many-to-many association table for Quiz <-> Tag
quiz_tags = Table(
    "quiz_tags",
    Base.metadata,
    Column("quiz_id", UUID, ForeignKey("quizzes.quiz_id"), primary_key=True),
    Column("tag_id", UUID, ForeignKey("tags.tag_id"), primary_key=True),
)

# Many-to-many association table for User <-> Quiz favorites
quiz_favorites = Table(
    "quiz_favorites",
    Base.metadata,
    Column(
        "user_id", UUID, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "quiz_id",
        UUID,
        ForeignKey("quizzes.quiz_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("created_at", DateTime, default=func.now()),
)


class Tag(Base):
    """Tags for categorizing quizzes."""

    __tablename__ = "tags"

    tag_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    name = Column(VARCHAR(30), nullable=False, unique=True, index=True)

    quizzes = relationship("Quiz", secondary=quiz_tags, back_populates="tags")


class Quiz(Base):
    __tablename__ = "quizzes"

    quiz_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    creator_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    creator = relationship("User", back_populates="quizzes")

    title = Column(VARCHAR(50), nullable=False)
    description = Column(VARCHAR(300), nullable=True)

    # Settings (randomize_questions, randomize_answers, show_immediate_feedback moved to room/session level)
    default_time_per_question = Column(
        Integer, default=30_000
    )  # UI preset, milliseconds
    visibility = Column(
        Enum(QuizVisibility, name="quiz_visibility"),
        nullable=False,
        default=QuizVisibility.public,
    )
    status = Column(
        Enum(QuizStatus, name="quiz_status"),
        nullable=False,
        default=QuizStatus.draft,
    )
    max_participants = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    questions = relationship(
        "QuizQuestion",
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizQuestion.position",
    )
    tags = relationship("Tag", secondary=quiz_tags, back_populates="quizzes")
    favorited_by = relationship(
        "User", secondary="quiz_favorites", back_populates="favorite_quizzes"
    )


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    question_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    quiz_id = Column(UUID, ForeignKey("quizzes.quiz_id"), nullable=False, index=True)
    text = Column(VARCHAR(255), nullable=False)
    position = Column(
        Integer, nullable=False, default=1
    )  # For drag & drop ordering (1-indexed)
    time_limit = Column(
        Integer, nullable=False, default=30_000
    )  # Per-question time in ms

    quiz = relationship("Quiz", back_populates="questions")
    answers = relationship(
        "QuizAnswer",
        back_populates="question",
        cascade="all, delete-orphan",
        foreign_keys="QuizAnswer.question_id",
    )


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"

    answer_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    question_id = Column(
        UUID,
        ForeignKey("quiz_questions.question_id", name="fk_answer_question"),
        nullable=False,
    )
    text = Column(VARCHAR(255), nullable=False)
    is_correct = Column(Boolean, default=False, nullable=False)

    question = relationship(
        "QuizQuestion", back_populates="answers", foreign_keys=[question_id]
    )
