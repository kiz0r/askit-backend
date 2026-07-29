from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    JWT_ACCESS_SECRET: str = Field(..., min_length=32)
    JWT_REFRESH_SECRET: str = Field(..., min_length=32)

    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    APP_PORT: int = 8000

    # Logging Settings
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_JSON: bool = False  # Set to True in production for JSON logs

    # CORS Settings
    CORS_ORIGINS: str = Field(
        default="http://localhost:5173",
        description="Comma-separated list of allowed CORS origins",
    )

    POSTGRES_USER: str = Field(..., min_length=3)
    POSTGRES_PASSWORD: str = Field(..., min_length=3)
    POSTGRES_DB: str = Field(..., min_length=3)
    POSTGRES_HOST: str = Field(..., min_length=3)
    POSTGRES_PORT: int = 5432

    DB_POOL_SIZE: int = Field(
        default=20,
        ge=1,
        description="Connections kept open per process. Must cover the WebSocket "
        "connections of a full game room plus concurrent HTTP requests.",
    )
    DB_MAX_OVERFLOW: int = Field(
        default=30,
        ge=0,
        description="Extra connections opened above DB_POOL_SIZE under load.",
    )

    # Redis Settings
    REDIS_HOST: str = Field(default="redis")
    REDIS_PORT: int = Field(default=6379)
    REDIS_DB: int = Field(
        default=0,
        ge=0,
        description="Redis logical database. The test suite uses a separate one "
        "so a test run never touches development game state.",
    )

    model_config = SettingsConfigDict(env_file=".env")

    @property
    def database_url(self) -> str:
        """Build PostgreSQL async database URL."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        """Build Redis URL."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS string into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


ENV_SETTINGS = Settings()


def is_dev() -> bool:
    return ENV_SETTINGS.ENVIRONMENT == "development"


def is_production() -> bool:
    return ENV_SETTINGS.ENVIRONMENT == "production"
