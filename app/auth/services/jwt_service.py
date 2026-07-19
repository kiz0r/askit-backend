from datetime import datetime, timezone, timedelta
from typing import TypedDict

from jwt import ExpiredSignatureError, InvalidTokenError as JWTInvalidTokenError
from attrs import frozen

import jwt

from app.settings import ENV_SETTINGS
from app.auth.exceptions import TokenExpiredError, InvalidTokenError


class JWTPayload(TypedDict):
    sub: str
    type: str
    iat: int
    exp: int


@frozen
class JWTService:
    access_token_lifetime: int = 3600
    refresh_token_lifetime: int = 60 * 60 * 24 * 7
    _access_secret: str = ENV_SETTINGS.JWT_ACCESS_SECRET
    _refresh_secret: str = ENV_SETTINGS.JWT_REFRESH_SECRET
    _algorithm: str = "HS256"

    def _create_token(
        self, subject: str, token_type: str, key: str, expires_in: int
    ) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": subject,
            "type": token_type,
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
        }
        return str(jwt.encode(payload, key, algorithm=self._algorithm))

    def create_access_token(self, user_id: str) -> str:
        return self._create_token(
            subject=user_id,
            token_type="access",
            key=self._access_secret,
            expires_in=self.access_token_lifetime,
        )

    def create_refresh_token(self, user_id: str) -> str:
        return self._create_token(
            subject=user_id,
            token_type="refresh",
            key=self._refresh_secret,
            expires_in=self.refresh_token_lifetime,
        )

    def verify_access_token(self, token: str) -> JWTPayload:
        return self._decode(token, self._access_secret, "access")

    def verify_refresh_token(self, token: str) -> JWTPayload:
        return self._decode(token, self._refresh_secret, "refresh")

    def _decode(self, token: str, key: str, expected_type: str) -> JWTPayload:
        try:
            raw = jwt.decode(token, key, algorithms=[self._algorithm])
            if raw.get("type") != expected_type:
                raise InvalidTokenError()
            return JWTPayload(
                sub=raw["sub"], type=raw["type"], iat=raw["iat"], exp=raw["exp"]
            )
        except ExpiredSignatureError:
            raise TokenExpiredError()
        except JWTInvalidTokenError:
            raise InvalidTokenError()


jwt_service = JWTService()
