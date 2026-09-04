import asyncio
from unittest.mock import AsyncMock

import pytest

from app.domain.place import Place
from app.engine.price_discovery.source_discovery import discover_sources
from app.integrations.gemini import GroundingCitation, GroundingResult, GroundingUnavailableError


def _place() -> Place:
    return Place(id=1, name="냉삼가게", address="충남 아산시", geom="fake-geom")


class _FakeClient:
    def __init__(self, result=None, error: GroundingUnavailableError | None = None):
        self._result = result
        self._error = error
        self.ground_search = AsyncMock(side_effect=self._call)

    async def _call(self, query: str):
        if self._error is not None:
            raise self._error
        return self._result


def test_discover_sources_returns_none_when_citations_empty():
    client = _FakeClient(result=GroundingResult(text="못 찾음", citations=[]))
    assert asyncio.run(discover_sources(_place(), client)) is None


def test_discover_sources_returns_result_when_citations_present():
    grounding = GroundingResult(
        text="확인됨", citations=[GroundingCitation(url="https://example.com", title="공식")]
    )
    client = _FakeClient(result=grounding)
    result = asyncio.run(discover_sources(_place(), client))
    assert result is grounding


def test_discover_sources_propagates_request_failure_instead_of_swallowing_it():
    # 실사용 중 발견(2026-08-31): 요청 실패("자료를 못 찾음")와 구분해야 하므로
    # 여기서 None으로 삼키지 않고 그대로 올려보낸다 — orchestrator가 구분된
    # error_code를 남길 수 있게.
    client = _FakeClient(error=GroundingUnavailableError("HTTP_500"))
    with pytest.raises(GroundingUnavailableError) as exc_info:
        asyncio.run(discover_sources(_place(), client))
    assert exc_info.value.reason == "HTTP_500"
