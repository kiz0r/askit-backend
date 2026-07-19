"""Input validators for authentication data."""

import re

from app.auth.exceptions import InvalidPasswordError, InvalidUsernameError


class AuthValidators:
    """Validators for authentication input data."""

    _USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,30}$")

    @staticmethod
    def validate_username(username: str) -> str:
        """
        Validate username format.

        Rules:
        - 3-30 characters
        - Only letters, numbers, and underscores
        - No spaces or special characters

        Args:
            username: Username to validate

        Returns:
            str: Valid username

        Raises:
            InvalidUsernameError: If username is invalid
        """
        if not username:
            raise InvalidUsernameError("Username is required")

        if len(username) < 3:
            raise InvalidUsernameError("Username must be at least 3 characters long")

        if len(username) > 30:
            raise InvalidUsernameError("Username must not exceed 30 characters")

        if not AuthValidators._USERNAME_PATTERN.match(username):
            raise InvalidUsernameError(
                "Username can only contain letters, numbers, and underscores"
            )

        return username

    @staticmethod
    def validate_password(password: str) -> str:
        """
        Validate password format.

        Rules:
        - Minimum 8 characters
        - At least one letter
        - At least one number
        - At least one special character (optional but recommended)

        Args:
            password: Password to validate

        Returns:
            str: Valid password

        Raises:
            InvalidPasswordError: If password is invalid
        """
        if not password:
            raise InvalidPasswordError("Password is required")

        if len(password) < 8:
            raise InvalidPasswordError("Password must be at least 8 characters long")

        if len(password) > 128:
            raise InvalidPasswordError("Password must not exceed 128 characters")

        if not re.search(r"[A-Za-z]", password):
            raise InvalidPasswordError("Password must contain at least one letter")

        if not re.search(r"\d", password):
            raise InvalidPasswordError("Password must contain at least one number")

        # Check for at least one special character (recommended)
        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\/;~`]', password):
            raise InvalidPasswordError(
                "Password must contain at least one special character (!@#$%^&* etc.)"
            )

        return password
