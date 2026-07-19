"""Core application exceptions."""

from fastapi import status


# Type alias for error details - values can be str, int, bool, or nested structures
ErrorDetails = dict[str, str | int | bool | list[str] | dict[str, str]]


class AppException(Exception):
    """Base application exception with structured error response."""

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: ErrorDetails | None = None,
    ) -> None:
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details: ErrorDetails = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, str | ErrorDetails]:
        """Convert exception to dictionary format."""
        error_dict: dict[str, str | ErrorDetails] = {
            "errorCode": self.error_code,
            "message": self.message,
        }
        if self.details:
            error_dict["details"] = self.details
        return error_dict
