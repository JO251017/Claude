from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Supabase's transaction pooler (port 6543, PgBouncer/Supavisor transaction mode) doesn't
# support asyncpg's server-side prepared statement cache — connections are handed out per
# transaction, so a cached statement can point at a different backend on the next query.
# statement_cache_size=0 disables that cache so every query is sent unprepared.
#
# timeout(연결 시도 자체의 타임아웃)이 없으면 DB가 응답 없을 때 연결 시도가 OS
# 기본값(수십 초)까지 그냥 걸린다 — /health/deps처럼 "빨리 실패해야 의미 있는"
# 헬스체크가 60초 넘게 멈추는 걸 실제로 확인했다(2026-08-12, 로컬에 DB가 없는
# 상태에서 재현). Render의 헬스체크나 이 프로젝트의 keep-alive 핑도 이 엔드포인트를
# 쓰므로, 연결이 안 될 땐 몇 초 안에 실패로 답해야 한다.
engine = create_async_engine(
    settings.supabase_db_url,
    pool_pre_ping=True,
    future=True,
    connect_args={"statement_cache_size": 0, "timeout": 10},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
