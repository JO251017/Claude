import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.dedupe import dedupe
from app.ingestion.normalize import NormalizedOffer
from app.ingestion.upsert import upsert_offers
from app.ingestion.validate import ValidationError, validate
from app.sources.public_api.adapters import ADAPTERS

logger = logging.getLogger(__name__)


async def sync_all_public_sources(session: AsyncSession) -> dict:
    """등록된 공공데이터 어댑터를 전부 수집 → 검증 → 중복제거 → 저장한다.

    스펙이 아직 확인되지 않은 어댑터(NotImplementedError)는 건너뛰고 결과에 기록만 남긴다 —
    확인 안 된 API를 지어내지 않는다는 원칙 때문에 현재는 PublicParkingAdapter만 실제로 수집된다.
    """
    collected: list[NormalizedOffer] = []
    skipped: list[dict] = []

    for adapter_cls in ADAPTERS:
        adapter = adapter_cls()
        try:
            offers = await adapter.collect()
        except NotImplementedError as exc:
            skipped.append({"adapter": adapter_cls.__name__, "reason": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001 - 한 소스 실패가 전체 동기화를 막으면 안 됨
            logger.warning("공공데이터 수집 실패: %s: %s", adapter_cls.__name__, exc)
            skipped.append({"adapter": adapter_cls.__name__, "reason": f"수집 실패: {exc}"})
            continue
        collected.extend(offers)

    valid: list[NormalizedOffer] = []
    invalid_count = 0
    for offer in collected:
        try:
            valid.append(validate(offer))
        except ValidationError:
            invalid_count += 1

    deduped = dedupe(valid)
    inserted = await upsert_offers(session, deduped)

    return {
        "collected": len(collected),
        "invalid": invalid_count,
        "inserted": inserted,
        "skipped_adapters": skipped,
    }
