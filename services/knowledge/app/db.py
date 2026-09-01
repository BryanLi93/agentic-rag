from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings
from typing import AsyncGenerator

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖项:每个请求注入一个 AsyncSession,请求结束自动关闭。"""
    async with AsyncSessionLocal() as session:
        yield session
