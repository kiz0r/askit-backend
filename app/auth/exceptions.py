"""Authentication and authorization exceptions."""

from fastapi import status

from app.core.exceptions import AppException, ErrorDetails


# =============================================================================
# Authentication Errors (401)
# =============================================================================


class AuthenticationError(AppException):
    """Base authentication error."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: ErrorDetails | None = None,
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class InvalidCredentialsError(AuthenticationError):
    """Invalid email or password."""

    def __init__(self) -> None:
        super().__init__(
            error_code="INVALID_CREDENTIALS",
            message="Invalid email or password",
        )


class TokenExpiredError(AuthenticationError):
    """JWT token has expired."""

    def __init__(self) -> None:
        super().__init__(
            error_code="TOKEN_EXPIRED",
            message="Authentication token has expired",
        )


class InvalidTokenError(AuthenticationError):
    """Invalid JWT token."""

    def __init__(self) -> None:
        super().__init__(
            error_code="INVALID_TOKEN",
            message="Invalid authentication token",
        )


class NotAuthenticatedError(AuthenticationError):
    """User is not authenticated."""

    def __init__(self) -> None:
        super().__init__(
            error_code="NOT_AUTHENTICATED",
            message="Authentication required",
        )


class RefreshTokenMissingError(AuthenticationError):
    """Refresh token is missing."""

    def __init__(self) -> None:
        super().__init__(
            error_code="REFRESH_TOKEN_MISSING",
            message="Refresh token is required",
        )


# =============================================================================
# Authorization Errors (403)
# =============================================================================


class AuthorizationError(AppException):
    """Base authorization error."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: ErrorDetails | None = None,
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class UserInactiveError(AuthorizationError):
    """User account is inactive."""

    def __init__(self) -> None:
        super().__init__(
            error_code="USER_INACTIVE",
            message="User account is inactive",
        )


class InsufficientPermissionsError(AuthorizationError):
    """User doesn't have permission."""

    def __init__(self, resource: str = "resource") -> None:
        super().__init__(
            error_code="INSUFFICIENT_PERMISSIONS",
            message=f"You don't have permission to access this {resource}",
        )


# =============================================================================
# Validation Errors (422)
# =============================================================================


class AuthValidationError(AppException):
    """Base validation error for auth-related input."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: ErrorDetails | None = None,
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class InvalidUsernameError(AuthValidationError):
    """Invalid username format."""

    def __init__(
        self,
        message: str = "Username must be 3-30 characters, letters, numbers, and underscores only",
    ) -> None:
        super().__init__(error_code="INVALID_USERNAME", message=message)


class InvalidPasswordError(AuthValidationError):
    """Invalid password format."""

    def __init__(self, message: str) -> None:
        super().__init__(error_code="INVALID_PASSWORD", message=message)


class InvalidEmailError(AuthValidationError):
    """Invalid email format."""

    def __init__(self) -> None:
        super().__init__(
            error_code="INVALID_EMAIL",
            message="Invalid email format",
        )


# =============================================================================
# Resource Conflicts (409)
# =============================================================================


class UserAlreadyExistsError(AppException):
    """User with this email already exists."""

    def __init__(self) -> None:
        super().__init__(
            error_code="USER_ALREADY_EXISTS",
            message="User with this email already exists",
            status_code=status.HTTP_409_CONFLICT,
        )


class UsernameAlreadyExistsError(AppException):
    """Username already taken."""

    def __init__(self) -> None:
        super().__init__(
            error_code="USERNAME_ALREADY_EXISTS",
            message="Username already taken",
            status_code=status.HTTP_409_CONFLICT,
        )
