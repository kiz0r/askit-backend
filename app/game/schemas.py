"""Schemas for game sessions and WebSocket messages."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.game import GameSessionStatus


# =============================================================================
# REST API Schemas
# =============================================================================


class CreateRoomRequest(BaseModel):
    """Request to create a new game room."""

    quiz_id: str = Field(serialization_alias="quizId", validation_alias="quizId")
    randomize_questions: bool = Field(
        default=False,
        serialization_alias="randomizeQuestions",
        validation_alias="randomizeQuestions",
    )
    randomize_answers: bool = Field(
        default=False,
        serialization_alias="randomizeAnswers",
        validation_alias="randomizeAnswers",
    )
    show_immediate_feedback: bool = Field(
        default=True,
        serialization_alias="showImmediateFeedback",
        validation_alias="showImmediateFeedback",
    )

    model_config = {"populate_by_name": True}


class RoomResponse(BaseModel):
    """Response with room details."""

    session_id: str = Field(serialization_alias="sessionId")
    room_code: str = Field(serialization_alias="roomCode")
    quiz_id: str = Field(serialization_alias="quizId")
    status: GameSessionStatus
    player_count: int = Field(serialization_alias="playerCount")
    created_at: datetime = Field(serialization_alias="createdAt")

    model_config = {"populate_by_name": True}


class JoinRoomRequest(BaseModel):
    """Request to join a game room."""

    nickname: str = Field(min_length=1, max_length=30)


class PlayerInfo(BaseModel):
    """Player information."""

    player_id: str = Field(serialization_alias="playerId")
    nickname: str
    score: int = 0
    is_connected: bool = Field(default=True, serialization_alias="isConnected")

    model_config = {"populate_by_name": True}


# =============================================================================
# WebSocket Message Types
# =============================================================================


class WSMessageType(str, Enum):
    """WebSocket message types."""

    # Client → Server
    JOIN = "join"  # Player joining room
    LEAVE = "leave"  # Player leaving
    ANSWER = "answer"  # Player submitting answer
    START_GAME = "start_game"  # Host starting game
    NEXT_QUESTION = "next_question"  # Host moving to next question

    # Server → Client
    ERROR = "error"
    ROOM_STATE = "room_state"  # Full room state sync
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    GAME_STARTING = "game_starting"  # Countdown before first question
    QUESTION = "question"  # New question to display
    ANSWER_RESULT = "answer_result"  # Result of player's answer (if immediate feedback)
    QUESTION_ENDED = "question_ended"  # All answers in or time up
    LEADERBOARD = "leaderboard"  # Scores between questions
    GAME_FINISHED = "game_finished"  # Final results


# =============================================================================
# WebSocket Message Schemas
# =============================================================================


class WSMessage(BaseModel):
    """Base WebSocket message."""

    type: WSMessageType
    payload: dict[str, object] = Field(default_factory=dict)


class WSError(BaseModel):
    """Error message payload."""

    code: str
    message: str


class WSPlayerJoined(BaseModel):
    """Player joined payload."""

    player: PlayerInfo


class WSPlayerLeft(BaseModel):
    """Player left payload."""

    player_id: str = Field(serialization_alias="playerId")
    nickname: str

    model_config = {"populate_by_name": True}


class WSGameStarting(BaseModel):
    """Game starting payload."""

    countdown_seconds: int = Field(serialization_alias="countdownSeconds")
    total_questions: int = Field(serialization_alias="totalQuestions")

    model_config = {"populate_by_name": True}


class WSAnswerOption(BaseModel):
    """Answer option in a question."""

    answer_id: str = Field(serialization_alias="answerId")
    text: str

    model_config = {"populate_by_name": True}


class WSQuestion(BaseModel):
    """Question payload sent to players."""

    question_index: int = Field(serialization_alias="questionIndex")
    total_questions: int = Field(serialization_alias="totalQuestions")
    question_id: str = Field(serialization_alias="questionId")
    text: str
    answers: list[WSAnswerOption]
    time_limit_ms: int = Field(serialization_alias="timeLimitMs")
    started_at: datetime = Field(serialization_alias="startedAt")

    model_config = {"populate_by_name": True}


class WSAnswerSubmit(BaseModel):
    """Player's answer submission."""

    question_id: str = Field(
        serialization_alias="questionId", validation_alias="questionId"
    )
    answer_ids: list[str] = Field(
        serialization_alias="answerIds",
        validation_alias="answerIds",
    )

    model_config = {"populate_by_name": True}


class WSAnswerResult(BaseModel):
    """Result of player's answer (immediate feedback)."""

    is_correct: bool = Field(serialization_alias="isCorrect")
    correct_answer_ids: list[str] = Field(serialization_alias="correctAnswerIds")
    points_earned: int = Field(serialization_alias="pointsEarned")
    time_taken_ms: int = Field(serialization_alias="timeTakenMs")

    model_config = {"populate_by_name": True}


class WSQuestionEnded(BaseModel):
    """Question ended payload."""

    question_id: str = Field(serialization_alias="questionId")
    correct_answer_ids: list[str] = Field(serialization_alias="correctAnswerIds")
    answer_distribution: dict[str, int] = Field(
        default_factory=dict,
        serialization_alias="answerDistribution",
    )

    model_config = {"populate_by_name": True}


class WSLeaderboardEntry(BaseModel):
    """Leaderboard entry."""

    rank: int
    player_id: str = Field(serialization_alias="playerId")
    nickname: str
    score: int
    change: int = 0  # Position change from last leaderboard

    model_config = {"populate_by_name": True}


class WSLeaderboard(BaseModel):
    """Leaderboard payload."""

    entries: list[WSLeaderboardEntry]
    question_index: int = Field(serialization_alias="questionIndex")

    model_config = {"populate_by_name": True}


class WSGameFinished(BaseModel):
    """Game finished payload."""

    final_leaderboard: list[WSLeaderboardEntry] = Field(
        serialization_alias="finalLeaderboard"
    )
    total_questions: int = Field(serialization_alias="totalQuestions")
    duration_seconds: int = Field(serialization_alias="durationSeconds")

    model_config = {"populate_by_name": True}


class WSRoomState(BaseModel):
    """Full room state for sync."""

    session_id: str = Field(serialization_alias="sessionId")
    room_code: str = Field(serialization_alias="roomCode")
    status: GameSessionStatus
    host_id: str = Field(serialization_alias="hostId")
    players: list[PlayerInfo]
    quiz_title: str = Field(serialization_alias="quizTitle")
    total_questions: int = Field(serialization_alias="totalQuestions")
    current_question_index: int = Field(serialization_alias="currentQuestionIndex")

    model_config = {"populate_by_name": True}
