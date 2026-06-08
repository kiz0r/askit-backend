"""Game module exceptions."""

from fastapi import status
from app.core.exceptions import AppException


class RoomNotFoundError(AppException):
    """Game room not found."""

    def __init__(self) -> None:
        super().__init__(
            error_code="ROOM_NOT_FOUND",
            message="Game room not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class RoomFullError(AppException):
    """Game room is full."""

    def __init__(self) -> None:
        super().__init__(
            error_code="ROOM_FULL",
            message="Game room is full",
            status_code=status.HTTP_409_CONFLICT,
        )


class GameAlreadyStartedError(AppException):
    """Game has already started."""

    def __init__(self) -> None:
        super().__init__(
            error_code="GAME_ALREADY_STARTED",
            message="Game has already started",
            status_code=status.HTTP_409_CONFLICT,
        )


class NotHostError(AppException):
    """Only the host can perform this action."""

    def __init__(self) -> None:
        super().__init__(
            error_code="NOT_HOST",
            message="Only the host can perform this action",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class NicknameAlreadyTakenError(AppException):
    """Nickname is already taken in this room."""

    def __init__(self) -> None:
        super().__init__(
            error_code="NICKNAME_ALREADY_TAKEN",
            message="This nickname is already taken in this room",
            status_code=status.HTTP_409_CONFLICT,
        )


class InvalidRoomCodeError(AppException):
    """Invalid room code format."""

    def __init__(self) -> None:
        super().__init__(
            error_code="INVALID_ROOM_CODE",
            message="Invalid room code",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class PlayerNotFoundError(AppException):
    """Player not found in the game."""

    def __init__(self) -> None:
        super().__init__(
            error_code="PLAYER_NOT_FOUND",
            message="Player not found in this game",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class QuestionNotActiveError(AppException):
    """No question is currently active."""

    def __init__(self) -> None:
        super().__init__(
            error_code="QUESTION_NOT_ACTIVE",
            message="No question is currently active",
            status_code=status.HTTP_409_CONFLICT,
        )


class AlreadyAnsweredError(AppException):
    """Player has already answered this question."""

    def __init__(self) -> None:
        super().__init__(
            error_code="ALREADY_ANSWERED",
            message="You have already answered this question",
            status_code=status.HTTP_409_CONFLICT,
        )
