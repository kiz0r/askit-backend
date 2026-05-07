import structlog
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from slowapi.errors import RateLimitExceeded

from app.core.exceptions import AppException

logger = structlog.get_logger(__name__)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application exceptions and return flat structured response."""
    logger.warning(
        "application_exception",
        error_code=exc.error_code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        path=request.url.path,
    )
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors and return structured response.

    Converts Pydantic validation errors into our standard error format.
    """
    errors = exc.errors()

    # Build a human-readable message from all errors
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
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Handle Pydantic ValidationError from custom validators."""
    errors = exc.errors()

    # Build a human-readable message from all errors
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


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "errorCode": "RATE_LIMITED",
            "message": "Too many requests. Please try again later.",
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unexpected exceptions.

    In production, this prevents exposing internal error details.
    """
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
