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

    # Redis Settings
    REDIS_HOST: str = Field(default="redis")
    REDIS_PORT: int = Field(default=6379)

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
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS string into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


ENV_SETTINGS = Settings()


def is_dev() -> bool:
    return ENV_SETTINGS.ENVIRONMENT == "development"


def is_production() -> bool:
    return ENV_SETTINGS.ENVIRONMENT == "production"
