from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Supabase's transaction pooler (port 6543, PgBouncer/Supavisor transaction mode) doesn't
# support asyncpg's server-side prepared statement cache — connections are handed out per
# transaction, so a cached statement can point at a different backend on the next query.
# statement_cache_size=0 disables that cache so every query is sent unprepared.
engine = create_async_engine(
    settings.supabase_db_url,
    pool_pre_ping=True,
    future=True,
    connect_args={"statement_cache_size": 0},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
