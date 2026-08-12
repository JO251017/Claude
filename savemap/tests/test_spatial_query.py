import asyncio

from app.engine.spatial_query import query_within_radius


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
