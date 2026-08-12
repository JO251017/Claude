import asyncio

from app.engine.spatial_query import query_places_without_offer, query_within_radius


class _FakeResult:
    def all(self):
        return []


class _CapturingSession:
    """실제 DB 없이 query_within_radius가 만드는 SQL에 LIMIT이 실제로 들어가는지만
    확인한다 — PostGIS 없이는 진짜 실행 결과를 검증할 수 없으니, 여기선 딱
    "row_limit을 넘기면 쿼리에 LIMIT절이 반영되는가"만 본다(밀집 지역에서 DB가
    무제한으로 행을 반환하는 걸 막는 안전판이 실제로 적용되는지)."""

    def __init__(self):
        self.compiled_sql: str | None = None

    async def execute(self, stmt, *a, **kw):
        self.compiled_sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        return _FakeResult()


def test_row_limit_adds_limit_clause_to_query():
    session = _CapturingSession()
    asyncio.run(query_within_radius(session, 36.99, 127.11, 3.0, row_limit=500))
    assert "LIMIT" in session.compiled_sql.upper()


def test_no_row_limit_by_default():
    # 기존 호출부(row_limit 안 넘기는 곳)가 있다면 동작이 안 바뀌어야 한다 — LIMIT절이
    # 생기지 않아야 함.
    session = _CapturingSession()
    asyncio.run(query_within_radius(session, 36.99, 127.11, 3.0))
    assert "LIMIT" not in session.compiled_sql.upper()


class _LiteralCapturingSession(_CapturingSession):
    """WHERE절에 들어간 실제 문자열 리터럴(카테고리 키워드 등)까지 확인해야 하는
    테스트용 — 기본 캡처는 파라미터를 바인드플레이스홀더로만 남기므로 값 자체는
    literal_binds=True로 다시 컴파일해야 보인다."""

    async def execute(self, stmt, *a, **kw):
        self.compiled_sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        return _FakeResult()


def test_query_within_radius_excludes_salon_categories():
    # 미용실/이용업(이발소) 비활성화(사용자 지시, 2026-08-12) — Place는 지우지 않고
    # 검색 쿼리 단계에서 걸러낸다.
    session = _LiteralCapturingSession()
    asyncio.run(query_within_radius(session, 36.99, 127.11, 3.0))
    assert "미용업" in session.compiled_sql
    assert "이용업" in session.compiled_sql


def test_query_places_without_offer_excludes_salon_categories():
    session = _LiteralCapturingSession()
    asyncio.run(query_places_without_offer(session, 36.99, 127.11, 3.0))
    assert "미용업" in session.compiled_sql
    assert "이용업" in session.compiled_sql
