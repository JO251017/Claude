"""EXCHANGE 재도입(SaveMap 구조 재설계 제안서 §07, 2026-08-13) — SavingsAsset의
offer_id/place_id/place_name 연결이 서비스 레이어에서 실제로 채워지는지, 그리고
새/기존 두 자산 생성 경로 모두 라우터 인증이 지켜지는지를 확인한다."""

import asyncio

import pytest

from app.core.errors import AssetNotFoundError
from app.exchange.service import create_asset, delete_asset


class _FakeSession:
    def __init__(self):
        self.added = None

    def add(self, obj):
        self.added = obj

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


def _patched_savings_asset(monkeypatch):
    # 실제 SavingsAsset(ORM 모델) 대신 kwargs를 그대로 속성으로 갖는 단순 객체를
    # 써서, DB/매핑 설정 없이 서비스 함수의 인자 전달만 검증한다.
    import app.exchange.service as service_module

    class _Recorder:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    monkeypatch.setattr(service_module, "SavingsAsset", _Recorder)


def test_create_asset_without_offer_link_leaves_new_fields_null(monkeypatch):
    # 기존 자유입력 등록 폼은 offer_id/place_id/place_name을 안 보낸다 — 기본값
    # None으로 하위호환이 유지되는지 확인.
    _patched_savings_asset(monkeypatch)
    session = _FakeSession()

    asset = asyncio.run(
        create_asset(
            session,
            owner_user_id="user-1",
            category="cafe",
            title="아메리카노 쿠폰",
            condition_text="1잔",
            estimated_value=4500.0,
            expires_at=None,
        )
    )
    assert asset.offer_id is None
    assert asset.place_id is None
    assert asset.place_name is None
    assert session.added is asset


def test_create_asset_with_offer_link_populates_all_three_fields():
    # 오퍼 상세 "저장하기"는 세 필드를 모두 채워서 넘긴다.
    session = _FakeSession()

    asset = asyncio.run(
        create_asset(
            session,
            owner_user_id="user-1",
            category="etc",
            title="행복카페",
            condition_text="아메리카노 4,500원",
            estimated_value=1500.0,
            expires_at=None,
            offer_id=42,
            place_id=7,
            place_name="행복카페",
        )
    )
    assert asset.offer_id == 42
    assert asset.place_id == 7
    assert asset.place_name == "행복카페"


def test_delete_asset_raises_when_not_owned():
    # _get_owned_asset이 owner_user_id로도 걸러야 한다 — 다른 사람 자산은
    # AssetNotFoundError로 취급(존재 여부를 노출하지 않음).
    class _EmptyResult:
        def scalar_one_or_none(self):
            return None

    class _EmptySession:
        async def execute(self, *a, **kw):
            return _EmptyResult()

    with pytest.raises(AssetNotFoundError):
        asyncio.run(delete_asset(_EmptySession(), "user-1", 999))


def test_create_asset_requires_auth(client):
    resp = client.post("/v1/exchange/assets", json={"category": "etc", "title": "x"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


def test_delete_asset_requires_auth(client):
    resp = client.delete("/v1/exchange/assets/1")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SM4011"


def test_list_assets_does_not_require_auth(client):
    # 둘러보기는 로그인 없이도 가능해야 한다(화면 안내 문구와 일치). NullSession은
    # DB 쿼리 자체를 막아두므로(session.execute → NotImplementedError), 빈 결과를
    # 돌려주는 가짜 세션으로 바꿔서 401로 막히지 않는지 + 정상 200을 확인한다.
    from app.api.deps import db_session
    from app.main import app

    class _EmptyScalars:
        def all(self):
            return []

    class _EmptyResult:
        def scalars(self):
            return _EmptyScalars()

    class _FakeListSession:
        async def execute(self, *a, **kw):
            return _EmptyResult()

    async def _fake_db_session():
        yield _FakeListSession()

    app.dependency_overrides[db_session] = _fake_db_session
    try:
        resp = client.get("/v1/exchange/assets")
    finally:
        app.dependency_overrides.pop(db_session, None)

    assert resp.status_code == 200
    assert resp.json() == []
