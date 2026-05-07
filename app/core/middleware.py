"""Middleware for request tracking and logging."""

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


class AutoRefreshMiddleware(BaseHTTPMiddleware):
    """
    Middleware that automatically refreshes expired access tokens.

    When an access token is expired but the refresh token is still valid,
    the middleware will:
    1. Generate a new access token
    2. Inject it into the request for the current handler
    3. Set the new token cookie in the response

    This eliminates the need for frontend retry logic on 401 responses.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = structlog.get_logger(__name__)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        access_token = request.cookies.get("access_token")
        refresh_token = request.cookies.get("refresh_token")
        new_access_token = None

        if access_token:
            try:
                jwt_service.verify_access_token(access_token)
            except TokenExpiredError:
                # Access token expired - try to refresh
                if refresh_token:
                    try:
                        payload = jwt_service.verify_refresh_token(refresh_token)
                        new_access_token = jwt_service.create_access_token(
                            payload["sub"]
                        )

                        # Inject new token into request cookies for this request
                        # Create a mutable copy of cookies
                        request.scope["headers"] = [
                            (name, value)
                            for name, value in request.scope["headers"]
                            if name != b"cookie"
                        ]
                        # Rebuild cookie header with new access token
                        cookies = dict(request.cookies)
                        cookies["access_token"] = new_access_token
                        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
                        request.scope["headers"].append(
                            (b"cookie", cookie_str.encode())
                        )

                        self.logger.info(
                            "access_token_auto_refreshed", user_id=payload["sub"]
                        )
                    except (TokenExpiredError, InvalidTokenError):
                        # Refresh token also invalid - let request fail with 401
                        self.logger.debug(
                            "auto_refresh_failed", reason="refresh_token_invalid"
                        )
                    except Exception as e:
                        self.logger.warning("auto_refresh_error", error=str(e))
            except InvalidTokenError:
                # Token is invalid (not just expired) - don't try to refresh
                pass

        response = await call_next(request)

        # Set new access token in response if refreshed
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
    """
    Middleware that adds a unique request ID to each request.

    The request ID is:
    - Added to the request state
    - Added to structlog context (appears in all logs)
    - Added to response headers (X-Request-ID)
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = structlog.get_logger(__name__)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Store in request state for access in endpoints
        request.state.request_id = request_id

        # Add to structlog context - will appear in all logs during this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_host=request.client.host if request.client else None,
        )

        # Log request start
        start_time = time.time()
        self.logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            query_params=str(request.query_params) if request.query_params else None,
        )

        try:
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Log request completion
            self.logger.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2),
            )

            # Add request ID to response headers
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
            # Clear context after request
            structlog.contextvars.clear_contextvars()
