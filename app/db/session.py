from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession
)
from app.core.config import settings


DATABASE_URL = f'postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASS}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}'


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True
)


AsyncSessionLocal: AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
