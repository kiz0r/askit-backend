import enum
import secrets
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, VARCHAR, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.quiz import Quiz, QuizQuestion
    from app.models.user import User


def generate_room_code(length: int = 6) -> str:
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class GameSessionStatus(str, enum.Enum):
    waiting = "waiting"
    starting = "starting"
    question = "question"
    revealing = "revealing"
    leaderboard = "leaderboard"
    finished = "finished"


class GameSession(Base):
    __tablename__ = "game_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    room_code: Mapped[str] = mapped_column(
        VARCHAR(6), unique=True, index=True, default=generate_room_code
    )

    quiz_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quizzes.quiz_id"))
    host_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    randomize_questions: Mapped[bool] = mapped_column(default=False)
    randomize_answers: Mapped[bool] = mapped_column(default=False)
    show_immediate_feedback: Mapped[bool] = mapped_column(default=True)

    status: Mapped[GameSessionStatus] = mapped_column(default=GameSessionStatus.waiting)
    current_question_index: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)

    quiz: Mapped["Quiz"] = relationship("Quiz")
    host: Mapped["User"] = relationship("User")
    players: Mapped[list["GamePlayer"]] = relationship(
        "GamePlayer",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class GamePlayer(Base):
    __tablename__ = "game_players"

    player_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_sessions.session_id"), index=True
    )

    nickname: Mapped[str] = mapped_column(VARCHAR(30))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )

    score: Mapped[int] = mapped_column(Integer, default=0)
    is_connected: Mapped[bool] = mapped_column(default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    session: Mapped["GameSession"] = relationship(
        "GameSession", back_populates="players"
    )
    user: Mapped["User | None"] = relationship("User")
    answers: Mapped[list["GamePlayerAnswer"]] = relationship(
        "GamePlayerAnswer",
        back_populates="player",
        cascade="all, delete-orphan",
    )


class GamePlayerAnswer(Base):
    __tablename__ = "game_player_answers"

    answer_record_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_players.player_id"), index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quiz_questions.question_id", ondelete="CASCADE")
    )

    selected_answer_ids: Mapped[str] = mapped_column(VARCHAR(1000))
    is_correct: Mapped[bool] = mapped_column()
    time_taken_ms: Mapped[int] = mapped_column(Integer)
    points_earned: Mapped[int] = mapped_column(Integer, default=0)

    answered_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    player: Mapped["GamePlayer"] = relationship("GamePlayer", back_populates="answers")
    question: Mapped["QuizQuestion"] = relationship("QuizQuestion")
