from typing import cast

import structlog
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.exceptions import AppException

logger = structlog.get_logger(__name__)


async def app_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    app_exc = cast(AppException, exc)
    logger.warning(
        "application_exception",
        error_code=app_exc.error_code,
        message=app_exc.message,
        status_code=app_exc.status_code,
        details=app_exc.details,
        path=request.url.path,
    )
    return JSONResponse(status_code=app_exc.status_code, content=app_exc.to_dict())


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    validation_exc = cast(RequestValidationError, exc)
    errors = validation_exc.errors()

    if len(errors) == 1:
        error = errors[0]
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        message = f"{field}: {error['msg']}" if field else error["msg"]
    else:
        field_msgs = []
        for error in errors:
            field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
            field_msgs.append(field if field else error["msg"])
        message = f"Invalid fields: {', '.join(field_msgs)}"

    logger.warning(
        "validation_error",
        error_count=len(errors),
        message=message,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "errorCode": "VALIDATION_ERROR",
            "message": message,
        },
    )


async def pydantic_validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    validation_exc = cast(ValidationError, exc)
    errors = validation_exc.errors()

    if len(errors) == 1:
        error = errors[0]
        field = ".".join(str(loc) for loc in error["loc"])
        message = f"{field}: {error['msg']}" if field else error["msg"]
    else:
        field_msgs = []
        for error in errors:
            field = ".".join(str(loc) for loc in error["loc"])
            field_msgs.append(field if field else error["msg"])
        message = f"Invalid fields: {', '.join(field_msgs)}"

    logger.warning(
        "pydantic_validation_error",
        error_count=len(errors),
        message=message,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "errorCode": "VALIDATION_ERROR",
            "message": message,
        },
    )


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "errorCode": "RATE_LIMITED",
            "message": "Too many requests. Please try again later.",
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        exc_info=exc,
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "errorCode": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred. Please try again later.",
        },
    )
