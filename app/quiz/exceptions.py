"""Quiz module exceptions."""

from fastapi import status
from app.core.exceptions import AppException


class QuizNotFoundError(AppException):
    """Quiz not found."""

    def __init__(self) -> None:
        super().__init__(
            error_code="QUIZ_NOT_FOUND",
            message="Quiz not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class QuizAccessDeniedError(AppException):
    """User cannot access or modify this quiz."""

    def __init__(self) -> None:
        super().__init__(
            error_code="QUIZ_ACCESS_DENIED",
            message="You don't have permission to access or modify this quiz",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class InvalidQuizDataError(AppException):
    """Invalid quiz data (title, description, tags, questions, etc.)."""

    def __init__(self, message: str):
        super().__init__(
            error_code="INVALID_QUIZ_DATA",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class QuizPublishedError(AppException):
    """Cannot modify a quiz while it is published."""

    def __init__(self) -> None:
        super().__init__(
            error_code="QUIZ_PUBLISHED",
            message="This quiz is published. Move it to draft before editing.",
            status_code=status.HTTP_409_CONFLICT,
        )


class QuizNotPlayableError(AppException):
    """Cannot start a game for a quiz that is not published."""

    def __init__(self) -> None:
        super().__init__(
            error_code="QUIZ_NOT_PLAYABLE",
            message="This quiz is not published and cannot be played.",
            status_code=status.HTTP_409_CONFLICT,
        )
