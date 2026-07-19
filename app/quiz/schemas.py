from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .exceptions import InvalidQuizDataError
from .types import AnswerId, QuestionId, QuizId

MAX_TITLE_LENGTH = 50
MAX_DESCRIPTION_LENGTH = 300
MAX_TAG_LENGTH = 30
MAX_TAGS_PER_QUIZ = 5

DEFAULT_MAX_PARTICIPANTS = 5
MAX_PARTICIPANTS_LIMIT = 30
DEFAULT_TIME_PER_QUESTION_MS = 30_000


class QuizVisibility(str, Enum):
    private = "private"
    public = "public"


class QuizStatus(str, Enum):
    draft = "draft"
    published = "published"


def _validate_title(v: str | None) -> str | None:
    if v is None:
        return None
    if not v.strip():
        raise InvalidQuizDataError("Quiz title cannot be empty")
    if len(v) > MAX_TITLE_LENGTH:
        raise InvalidQuizDataError(
            f"Quiz title must not exceed {MAX_TITLE_LENGTH} characters"
        )
    return v.strip()


def _validate_description(v: str | None) -> str | None:
    if v is None:
        return None
    if len(v) > MAX_DESCRIPTION_LENGTH:
        raise InvalidQuizDataError(
            f"Quiz description must not exceed {MAX_DESCRIPTION_LENGTH} characters"
        )
    return v


def _validate_tags(v: list[str] | None) -> list[str] | None:
    if v is None:
        return None
    validated = []
    for tag in v:
        tag = tag.strip().lower()
        if tag and len(tag) <= MAX_TAG_LENGTH:
            validated.append(tag)
    unique_tags = list(set(validated))
    if len(unique_tags) > MAX_TAGS_PER_QUIZ:
        raise InvalidQuizDataError(f"Maximum {MAX_TAGS_PER_QUIZ} tags allowed per quiz")
    return unique_tags


class QuizAnswerCreate(BaseModel):
    text: str
    is_correct: bool = Field(
        default=False, serialization_alias="isCorrect", validation_alias="isCorrect"
    )

    model_config = ConfigDict(populate_by_name=True)


class QuizQuestionCreate(BaseModel):
    text: str
    time_limit: int = Field(
        default=DEFAULT_TIME_PER_QUESTION_MS,
        ge=5000,
        le=300000,
        serialization_alias="timeLimit",
        validation_alias="timeLimit",
    )
    answers: list[QuizAnswerCreate]

    model_config = ConfigDict(populate_by_name=True)


class QuizSettingsCreate(BaseModel):
    default_time_per_question: int = Field(
        default=DEFAULT_TIME_PER_QUESTION_MS,
        serialization_alias="defaultTimePerQuestion",
        validation_alias="defaultTimePerQuestion",
    )
    visibility: QuizVisibility = QuizVisibility.public
    max_participants: int = Field(
        default=DEFAULT_MAX_PARTICIPANTS,
        ge=1,
        le=MAX_PARTICIPANTS_LIMIT,
        serialization_alias="maxParticipants",
        validation_alias="maxParticipants",
    )

    model_config = ConfigDict(populate_by_name=True)


class QuizCreate(BaseModel):
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    settings: QuizSettingsCreate
    questions: list[QuizQuestionCreate]

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        result = _validate_title(v)
        if result is None:
            raise InvalidQuizDataError("Quiz title is required")
        return result

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        return _validate_description(v)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        return _validate_tags(v) or []


class QuizUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    settings: QuizSettingsCreate | None = None
    questions: list[QuizQuestionCreate] | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        return _validate_title(v)

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        return _validate_description(v)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str] | None) -> list[str] | None:
        return _validate_tags(v)


class QuizAnswerOut(BaseModel):
    answer_id: AnswerId = Field(serialization_alias="answerId")
    text: str
    is_correct: bool = Field(default=False, serialization_alias="isCorrect")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class QuizQuestionOut(BaseModel):
    question_id: QuestionId = Field(serialization_alias="questionId")
    text: str
    position: int
    time_limit: int = Field(serialization_alias="timeLimit")
    answers: list[QuizAnswerOut]

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class QuizSettingsOut(BaseModel):
    default_time_per_question: int = Field(serialization_alias="defaultTimePerQuestion")
    visibility: QuizVisibility
    max_participants: int = Field(serialization_alias="maxParticipants")

    model_config = ConfigDict(populate_by_name=True)


class QuizOut(BaseModel):
    quiz_id: QuizId = Field(serialization_alias="quizId")
    creator_id: str = Field(serialization_alias="creatorId")
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: QuizStatus
    settings: QuizSettingsOut
    questions: list[QuizQuestionOut]
    estimated_time: int = Field(serialization_alias="estimatedTime")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
    is_favorited: bool = Field(default=False, serialization_alias="isFavorited")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class QuizListOut(BaseModel):
    items: list[QuizOut]
    total: int


class FavoriteActionResponse(BaseModel):
    quiz_id: str = Field(serialization_alias="quizId")
    is_favorited: bool = Field(serialization_alias="isFavorited")

    model_config = ConfigDict(populate_by_name=True)


class SetQuizStatusInput(BaseModel):
    status: QuizStatus


class BulkStatsRequest(BaseModel):
    quiz_ids: list[QuizId] = Field(alias="quizIds")

    model_config = ConfigDict(populate_by_name=True)


class TopPlayerOut(BaseModel):
    nickname: str
    score: int
    played_at: datetime = Field(serialization_alias="playedAt")

    model_config = ConfigDict(populate_by_name=True)


class QuizStatsOut(BaseModel):
    quiz_id: str = Field(serialization_alias="quizId")
    times_played: int = Field(serialization_alias="timesPlayed")
    total_players: int = Field(serialization_alias="totalPlayers")
    average_score: int = Field(serialization_alias="averageScore")
    average_duration_seconds: int = Field(serialization_alias="averageDurationSeconds")
    top_players: list[TopPlayerOut] = Field(serialization_alias="topPlayers")

    model_config = ConfigDict(populate_by_name=True)


class BulkStatsOut(BaseModel):
    items: list[QuizStatsOut]

    model_config = ConfigDict(populate_by_name=True)


class QuizAnswerExport(BaseModel):
    text: str
    is_correct: bool = Field(serialization_alias="isCorrect")

    model_config = ConfigDict(populate_by_name=True)


class QuizQuestionExport(BaseModel):
    text: str
    time_limit: int = Field(serialization_alias="timeLimit")
    answers: list[QuizAnswerExport]

    model_config = ConfigDict(populate_by_name=True)


class QuizSettingsExport(BaseModel):
    default_time_per_question: int = Field(serialization_alias="defaultTimePerQuestion")
    visibility: QuizVisibility
    max_participants: int = Field(serialization_alias="maxParticipants")

    model_config = ConfigDict(populate_by_name=True)


class QuizExportOut(BaseModel):
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    settings: QuizSettingsExport
    questions: list[QuizQuestionExport]

    model_config = ConfigDict(populate_by_name=True)
