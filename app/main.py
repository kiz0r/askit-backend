from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from slowapi.errors import RateLimitExceeded
from app.auth.router import router as auth_router
from app.core.exception_handlers import (
    app_exception_handler,
    generic_exception_handler,
    pydantic_validation_exception_handler,
    rate_limit_exceeded_handler,
    validation_exception_handler,
)
from app.core.exceptions import AppException
from app.core.limiter import limiter
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    AutoRefreshMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from app.database import init_db
from app.game.router import router as game_router
from app.game.router import ws_router
from app.quiz.router import router as quiz_router
from app.redis import close_redis, init_redis
from app.settings import ENV_SETTINGS
from app.user.router import router as user_router

# Configure structured logging
configure_logging(
    log_level=ENV_SETTINGS.LOG_LEVEL,
    use_json=ENV_SETTINGS.LOG_JSON,
)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "application_startup",
        environment=ENV_SETTINGS.ENVIRONMENT,
        port=ENV_SETTINGS.APP_PORT,
    )
    await init_db()
    await init_redis()
    logger.info("redis_connected", host=ENV_SETTINGS.REDIS_HOST)
    yield
    await close_redis()
    logger.info("application_shutdown")


app = FastAPI(
    title="AskIt! API",
    version="dev",
    lifespan=lifespan,
    redirect_slashes=False,
    generate_unique_id_function=lambda route: (
        f"{route.tags[0]}-{route.name}" if route.tags else route.name
    ),
)

app.state.limiter = limiter

# Register exception handlers
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(AutoRefreshMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ENV_SETTINGS.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(user_router, prefix="/api/v1/user")
app.include_router(quiz_router, prefix="/api/v1/quiz")
app.include_router(game_router, prefix="/api/v1/game")
app.include_router(ws_router, prefix="/ws")
