from fastapi import status

from app.core.exceptions import AppException, ErrorDetails


class AuthenticationError(AppException):
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
    def __init__(self) -> None:
        super().__init__(
            error_code="INVALID_CREDENTIALS",
            message="Invalid email or password",
        )


class TokenExpiredError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__(
            error_code="TOKEN_EXPIRED",
            message="Authentication token has expired",
        )


class InvalidTokenError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__(
            error_code="INVALID_TOKEN",
            message="Invalid authentication token",
        )


class TokenRevokedError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__(
            error_code="TOKEN_REVOKED",
            message="Token has been revoked",
        )


class NotAuthenticatedError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__(
            error_code="NOT_AUTHENTICATED",
            message="Authentication required",
        )


class RefreshTokenMissingError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__(
            error_code="REFRESH_TOKEN_MISSING",
            message="Refresh token is required",
        )


class AuthorizationError(AppException):
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
    def __init__(self) -> None:
        super().__init__(
            error_code="USER_INACTIVE",
            message="User account is inactive",
        )


class AuthValidationError(AppException):
    def __init__(
        self,
        error_code: str,
        message: str,
        details: ErrorDetails | None = None,
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=details,
        )


class InvalidUsernameError(AuthValidationError):
    def __init__(
        self,
        message: str = "Username must be 3-30 characters, letters, numbers, and underscores only",
    ) -> None:
        super().__init__(error_code="INVALID_USERNAME", message=message)


class InvalidPasswordError(AuthValidationError):
    def __init__(self, message: str) -> None:
        super().__init__(error_code="INVALID_PASSWORD", message=message)


class UsernameAlreadyExistsError(AppException):
    def __init__(self) -> None:
        super().__init__(
            error_code="USERNAME_ALREADY_EXISTS",
            message="Username already taken",
            status_code=status.HTTP_409_CONFLICT,
        )


class RegistrationFailedError(AppException):
    def __init__(self) -> None:
        super().__init__(
            error_code="REGISTRATION_FAILED",
            message="Registration failed. Email or username already in use.",
            status_code=status.HTTP_409_CONFLICT,
        )


class AccountLockedError(AppException):
    def __init__(self) -> None:
        super().__init__(
            error_code="ACCOUNT_LOCKED",
            message="Too many failed login attempts. Try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
