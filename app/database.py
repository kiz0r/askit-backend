from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.settings import ENV_SETTINGS


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    ENV_SETTINGS.database_url,
    echo=ENV_SETTINGS.LOG_LEVEL == "DEBUG",
    future=True,
)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
