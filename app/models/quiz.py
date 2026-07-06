import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    UUID,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Table,
    VARCHAR,
    Column,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.quiz.schemas import QuizStatus, QuizVisibility

if TYPE_CHECKING:
    from app.models.user import User


quiz_tags = Table(
    "quiz_tags",
    Base.metadata,
    Column("quiz_id", UUID, ForeignKey("quizzes.quiz_id"), primary_key=True),
    Column("tag_id", UUID, ForeignKey("tags.tag_id"), primary_key=True),
)

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
    __tablename__ = "tags"

    tag_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(VARCHAR(30), unique=True, index=True)

    quizzes: Mapped[list["Quiz"]] = relationship(
        "Quiz", secondary=quiz_tags, back_populates="tags"
    )


class Quiz(Base):
    __tablename__ = "quizzes"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    title: Mapped[str] = mapped_column(VARCHAR(50))
    description: Mapped[str | None] = mapped_column(VARCHAR(300))

    default_time_per_question: Mapped[int] = mapped_column(Integer, default=30_000)
    visibility: Mapped[QuizVisibility] = mapped_column(
        Enum(QuizVisibility, native_enum=False),
        default=QuizVisibility.public,
    )
    status: Mapped[QuizStatus] = mapped_column(
        Enum(QuizStatus, native_enum=False),
        default=QuizStatus.draft,
    )
    max_participants: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    creator: Mapped["User"] = relationship("User", back_populates="quizzes")
    questions: Mapped[list["QuizQuestion"]] = relationship(
        "QuizQuestion",
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizQuestion.position",
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary=quiz_tags, back_populates="quizzes"
    )
    favorited_by: Mapped[list["User"]] = relationship(
        "User", secondary="quiz_favorites", back_populates="favorite_quizzes"
    )


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    question_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quizzes.quiz_id"), index=True
    )
    text: Mapped[str] = mapped_column(VARCHAR(255))
    position: Mapped[int] = mapped_column(Integer, default=1)
    time_limit: Mapped[int] = mapped_column(Integer, default=30_000)
    allow_multiple_answers: Mapped[bool] = mapped_column(default=False)

    quiz: Mapped["Quiz"] = relationship("Quiz", back_populates="questions")
    answers: Mapped[list["QuizAnswer"]] = relationship(
        "QuizAnswer",
        back_populates="question",
        cascade="all, delete-orphan",
        foreign_keys="QuizAnswer.question_id",
    )


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"

    answer_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quiz_questions.question_id", name="fk_answer_question")
    )
    text: Mapped[str] = mapped_column(VARCHAR(255))
    is_correct: Mapped[bool] = mapped_column(default=False)

    question: Mapped["QuizQuestion"] = relationship(
        "QuizQuestion", back_populates="answers", foreign_keys=[question_id]
    )
