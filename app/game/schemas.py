from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from app.models.game import GameSessionStatus
from app.quiz.types import QuizId


class CreateRoomRequest(BaseModel):
    quiz_id: QuizId = Field(serialization_alias="quizId", validation_alias="quizId")
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
    public_results: bool = Field(
        default=True,
        serialization_alias="publicResults",
        validation_alias="publicResults",
    )

    model_config = {"populate_by_name": True}


class RoomResponse(BaseModel):
    session_id: str = Field(serialization_alias="sessionId")
    room_code: str = Field(serialization_alias="roomCode")
    quiz_id: str = Field(serialization_alias="quizId")
    status: GameSessionStatus
    player_count: int = Field(serialization_alias="playerCount")
    created_at: datetime = Field(serialization_alias="createdAt")

    model_config = {"populate_by_name": True}


class JoinRoomRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=30)


class PlayerInfo(BaseModel):
    player_id: str = Field(serialization_alias="playerId")
    nickname: str
    score: int = 0
    is_connected: bool = Field(default=True, serialization_alias="isConnected")

    model_config = {"populate_by_name": True}


class WSMessageType(str, Enum):
    # Client → Server
    ANSWER = "answer"
    START_GAME = "start_game"
    NEXT_QUESTION = "next_question"

    # Server → Client
    ERROR = "error"
    ROOM_STATE = "room_state"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    GAME_STARTING = "game_starting"
    QUESTION = "question"
    ANSWER_RESULT = "answer_result"
    PLAYER_ANSWERED = "player_answered"
    QUESTION_ENDED = "question_ended"
    GAME_FINISHED = "game_finished"
    HOST_ANSWER_UPDATE = "host_answer_update"


class WSError(BaseModel):
    code: str
    message: str


class WSPlayerJoined(BaseModel):
    player: PlayerInfo


class WSPlayerLeft(BaseModel):
    player_id: str = Field(serialization_alias="playerId")
    nickname: str

    model_config = {"populate_by_name": True}


class WSGameStarting(BaseModel):
    countdown_ms: int = Field(serialization_alias="countdownMs")
    total_questions: int = Field(serialization_alias="totalQuestions")

    model_config = {"populate_by_name": True}


class WSAnswerOption(BaseModel):
    answer_id: str = Field(serialization_alias="answerId")
    text: str

    model_config = {"populate_by_name": True}


class WSQuestion(BaseModel):
    question_index: int = Field(serialization_alias="questionIndex")
    total_questions: int = Field(serialization_alias="totalQuestions")
    question_id: str = Field(serialization_alias="questionId")
    text: str
    answers: list[WSAnswerOption]
    time_limit_ms: int = Field(serialization_alias="timeLimitMs")
    started_at: str = Field(serialization_alias="startedAt")
    allow_multiple_answers: bool = Field(
        default=False, serialization_alias="allowMultipleAnswers"
    )

    model_config = {"populate_by_name": True}


class WSAnswerSubmit(BaseModel):
    question_id: str = Field(
        serialization_alias="questionId", validation_alias="questionId"
    )
    answer_ids: list[str] = Field(
        serialization_alias="answerIds", validation_alias="answerIds"
    )

    model_config = {"populate_by_name": True}


class StartGameMessage(BaseModel):
    type: Literal[WSMessageType.START_GAME]


class NextQuestionMessage(BaseModel):
    type: Literal[WSMessageType.NEXT_QUESTION]


class AnswerClientMessage(BaseModel):
    type: Literal[WSMessageType.ANSWER]
    payload: WSAnswerSubmit


ClientMessage = Annotated[
    Union[StartGameMessage, NextQuestionMessage, AnswerClientMessage],
    Field(discriminator="type"),
]


class WSAnswerResult(BaseModel):
    is_correct: bool = Field(serialization_alias="isCorrect")
    correct_answer_ids: list[str] = Field(serialization_alias="correctAnswerIds")
    points_earned: int = Field(serialization_alias="pointsEarned")
    time_taken_ms: int = Field(serialization_alias="timeTakenMs")

    model_config = {"populate_by_name": True}


class WSPlayerAnswered(BaseModel):
    player_id: str = Field(serialization_alias="playerId")

    model_config = {"populate_by_name": True}


class WSQuestionEnded(BaseModel):
    question_id: str = Field(serialization_alias="questionId")
    correct_answer_ids: list[str] = Field(serialization_alias="correctAnswerIds")
    answer_distribution: dict[str, int] = Field(
        default_factory=dict,
        serialization_alias="answerDistribution",
    )
    leaderboard: list["WSLeaderboardEntry"] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class WSLeaderboardEntry(BaseModel):
    rank: int
    player_id: str = Field(serialization_alias="playerId")
    nickname: str
    score: int
    change: int = 0

    model_config = {"populate_by_name": True}


class WSGameFinished(BaseModel):
    final_leaderboard: list[WSLeaderboardEntry] = Field(
        serialization_alias="finalLeaderboard"
    )
    total_questions: int = Field(serialization_alias="totalQuestions")
    duration_ms: int = Field(serialization_alias="durationMs")
    public_results: bool = Field(default=True, serialization_alias="publicResults")

    model_config = {"populate_by_name": True}


class WSHostAnswerUpdate(BaseModel):
    player_id: str = Field(serialization_alias="playerId")
    nickname: str
    is_correct: bool = Field(serialization_alias="isCorrect")
    answer_ids: list[str] = Field(serialization_alias="answerIds")
    time_taken_ms: int = Field(serialization_alias="timeTakenMs")
    total_score: int = Field(serialization_alias="totalScore")

    model_config = {"populate_by_name": True}


class WSRoomState(BaseModel):
    session_id: str = Field(serialization_alias="sessionId")
    room_code: str = Field(serialization_alias="roomCode")
    status: GameSessionStatus
    host_id: str = Field(serialization_alias="hostId")
    players: list[PlayerInfo]
    quiz_title: str = Field(serialization_alias="quizTitle")
    total_questions: int = Field(serialization_alias="totalQuestions")
    current_question_index: int = Field(serialization_alias="currentQuestionIndex")
    current_question: WSQuestion | None = Field(
        default=None, serialization_alias="currentQuestion"
    )
    host_answer_details: list[WSHostAnswerUpdate] = Field(
        default_factory=list, serialization_alias="hostAnswerDetails"
    )
    question_ended: WSQuestionEnded | None = Field(
        default=None, serialization_alias="questionEnded"
    )

    model_config = {"populate_by_name": True}
