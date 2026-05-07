"""Game session models for real-time quiz gameplay."""

import enum
import secrets
import uuid

from sqlalchemy import (
    UUID,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    VARCHAR,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


def generate_room_code(length: int = 6) -> str:
    """Generate a random room code (uppercase letters + digits, no confusing chars)."""
    # Exclude confusing characters: 0, O, I, L, 1
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class GameSessionStatus(str, enum.Enum):
    """Game session lifecycle states."""

    waiting = "waiting"  # Lobby, waiting for players
    starting = "starting"  # Countdown before first question
    question = "question"  # Showing question, accepting answers
    revealing = "revealing"  # Showing correct answer
    leaderboard = "leaderboard"  # Showing scores between questions
    finished = "finished"  # Game over


class GameSession(Base):
    """
    A game session (room) where players compete.

    Lifecycle:
    1. Host creates room → waiting
    2. Players join with room_code
    3. Host starts → starting → question
    4. Cycle: question → revealing → leaderboard → question
    5. Last question → finished
    """

    __tablename__ = "game_sessions"

    session_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    # Room identification
    room_code = Column(
        VARCHAR(6),
        unique=True,
        nullable=False,
        index=True,
        default=generate_room_code,
    )

    # References
    quiz_id = Column(UUID, ForeignKey("quizzes.quiz_id"), nullable=False)
    host_id = Column(UUID, ForeignKey("users.id"), nullable=False)

    # Game settings (moved from quiz level)
    randomize_questions = Column(Boolean, default=False)
    randomize_answers = Column(Boolean, default=False)
    show_immediate_feedback = Column(Boolean, default=True)

    # Game state
    status = Column(
        Enum(GameSessionStatus, name="game_session_status"),
        nullable=False,
        default=GameSessionStatus.waiting,
    )
    current_question_index = Column(Integer, default=0)  # 0 = not started

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)

    # Relationships
    quiz = relationship("Quiz")
    host = relationship("User")
    players = relationship(
        "GamePlayer",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class GamePlayer(Base):
    """A player in a game session."""

    __tablename__ = "game_players"

    player_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    session_id = Column(
        UUID,
        ForeignKey("game_sessions.session_id"),
        nullable=False,
        index=True,
    )

    # Player identity
    nickname = Column(VARCHAR(30), nullable=False)
    user_id = Column(
        UUID, ForeignKey("users.id"), nullable=True
    )  # Optional if logged in

    # Game state
    score = Column(Integer, default=0)
    is_connected = Column(Boolean, default=True)
    joined_at = Column(DateTime, default=func.now())

    # Relationships
    session = relationship("GameSession", back_populates="players")
    user = relationship("User")
    answers = relationship(
        "GamePlayerAnswer",
        back_populates="player",
        cascade="all, delete-orphan",
    )


class GamePlayerAnswer(Base):
    """Records a player's answer to a question."""

    __tablename__ = "game_player_answers"

    answer_record_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    player_id = Column(
        UUID,
        ForeignKey("game_players.player_id"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        UUID,
        ForeignKey("quiz_questions.question_id"),
        nullable=False,
    )

    # Answer details
    selected_answer_ids = Column(VARCHAR(1000), nullable=False)  # JSON array of UUIDs
    is_correct = Column(Boolean, nullable=False)
    time_taken_ms = Column(Integer, nullable=False)  # Time to answer in ms
    points_earned = Column(Integer, default=0)

    answered_at = Column(DateTime, default=func.now())

    # Relationships
    player = relationship("GamePlayer", back_populates="answers")
    question = relationship("QuizQuestion")
