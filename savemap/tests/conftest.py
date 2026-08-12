"""라우트(엔드포인트) 레벨 테스트를 위한 공용 픽스처.

기존 테스트(99% 이상)는 세션을 흉내낸 FakeSession으로 서비스 함수 하나만 검증하는
순수 유닛테스트였다 — 실제 FastAPI 라우트에 요청을 보내서 검증(파라미터 검증, 인증
거부, 응답 스키마)하는 테스트가 하나도 없었다(2026-08-12 품질 점검에서 확인). 이
conftest는 실제 Postgres/PostGIS 없이도(샌드박스에 DB가 없다) 라우팅·인증·검증
계층을 TestClient로 실제로 두드려볼 수 있게 DB 세션만 갈아끼운다.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import db_session
from app.main import app


class NullSession:
    """실제 쿼리가 필요 없는 테스트(인증 거부, 입력 검증 등)용 최소 세션.
    쿼리가 실제로 필요한 테스트는 execute를 별도로 몽키패치해서 원하는 결과를 준다."""

    async def execute(self, *a, **kw):
        raise NotImplementedError(
            "이 라우트가 DB 쿼리를 실행했습니다 — 이 테스트가 검증하려는 게 쿼리 결과라면 "
            "session.execute를 몽키패치하세요 (인증/검증만 보는 테스트라면 라우트가 그 지점까지 "
            "가지 않는지 확인하세요)."
        )

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def refresh(self, obj):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def get(self, model, pk):
        return None


@pytest.fixture
def client():
    async def _override_db_session():
        yield NullSession()

    app.dependency_overrides[db_session] = _override_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
