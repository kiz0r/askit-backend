import uuid
import time
from typing import Callable, Awaitable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.auth.services.jwt_service import jwt_service
from app.auth.exceptions import TokenExpiredError, InvalidTokenError
from app.settings import is_dev


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        return response


class AutoRefreshMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = structlog.get_logger(__name__)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        from app.core.security import is_refresh_token_blacklisted

        access_token = request.cookies.get("access_token")
        refresh_token = request.cookies.get("refresh_token")
        new_access_token = None

        if access_token:
            try:
                jwt_service.verify_access_token(access_token)
            except TokenExpiredError:
                if refresh_token:
                    try:
                        if await is_refresh_token_blacklisted(refresh_token):
                            self.logger.debug(
                                "auto_refresh_skipped", reason="token_blacklisted"
                            )
                        else:
                            payload = jwt_service.verify_refresh_token(refresh_token)
                            new_access_token = jwt_service.create_access_token(
                                payload["sub"]
                            )

                            request.scope["headers"] = [
                                (name, value)
                                for name, value in request.scope["headers"]
                                if name != b"cookie"
                            ]
                            cookies = dict(request.cookies)
                            cookies["access_token"] = new_access_token
                            cookie_str = "; ".join(
                                f"{k}={v}" for k, v in cookies.items()
                            )
                            request.scope["headers"].append(
                                (b"cookie", cookie_str.encode())
                            )

                            self.logger.info(
                                "access_token_auto_refreshed", user_id=payload["sub"]
                            )
                    except (TokenExpiredError, InvalidTokenError):
                        self.logger.debug(
                            "auto_refresh_failed", reason="refresh_token_invalid"
                        )
                    except Exception as e:
                        self.logger.warning("auto_refresh_error", error=str(e))
            except InvalidTokenError:
                pass

        response = await call_next(request)

        if new_access_token:
            response.set_cookie(
                key="access_token",
                value=new_access_token,
                httponly=True,
                samesite="lax",
                secure=not is_dev(),
            )

        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = structlog.get_logger(__name__)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_host=request.client.host if request.client else None,
        )

        start_time = time.time()
        self.logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            query_params=str(request.query_params) if request.query_params else None,
        )

        try:
            response = await call_next(request)

            duration = time.time() - start_time

            self.logger.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2),
            )

            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as exc:
            duration = time.time() - start_time

            self.logger.error(
                "request_failed",
                exc_info=exc,
                duration_ms=round(duration * 1000, 2),
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()
