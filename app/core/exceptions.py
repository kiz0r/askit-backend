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


# Generic Resource Errors (for backwards compatibility)
class ResourceError(AppException):
    """Base resource error."""

    pass


class ResourceNotFoundError(ResourceError):
    """Resource not found."""

    def __init__(self, resource: str = "Resource"):
        super().__init__(
            error_code="RESOURCE_NOT_FOUND",
            message=f"{resource} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ResourceAlreadyExistsError(ResourceError):
    """Resource already exists."""

    def __init__(self, resource: str = "Resource"):
        super().__init__(
            error_code="RESOURCE_ALREADY_EXISTS",
            message=f"{resource} already exists",
            status_code=status.HTTP_409_CONFLICT,
        )
