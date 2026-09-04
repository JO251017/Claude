"""AI MVP §D(2026-09-01) — 펫 AI 반응.

기존 이벤트(발견/방문/추천/제보/인증/스트릭)에 대사를 붙이되, "AI 대화형 펫"은
만들지 않는다. 대사는 우선 프론트 템플릿을 그대로 쓰고(frontend/app.js의
PET_REACTION_LINES — 매 이벤트마다 AI를 부르면 §5 "AI 호출 비용 최소화"에
바로 어긋난다), 딱 하나 — 성장 단계가 실제로 올라간 "레벨업" 순간만 AI가
대사를 짓는다. 그 결과도 사용자별이 아니라 **단계(stage_index)당 전역으로
한 번만** 생성해 영구 캐시한다(app.domain.pet_reaction.PetStageMessage) — 앱
전체 수명 동안 이 기능이 Gemini를 부르는 횟수는 최대 "성장 단계 개수"번뿐이다.

허용된 mood/action(기존 CSS 클래스와 정확히 대응)을 이 모듈이 강제한다 — AI가
새 애니메이션 상태를 만들어내지 않는다는 원칙을 서버 쪽에서도 지킨다. 대사
텍스트는 15자 이내로 자르고, mood/action은 항상 "celebrate"/"celebrate"
고정이다(레벨업은 이 하나의 상황에서만 호출되므로 AI가 정할 필요가 없다 —
정할 게 있다면 그게 오히려 §D "AI가 새 애니메이션을 생성하지 않는다"는
원칙을 흔든다)."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.pet_reaction import PetStageMessage
from app.integrations.gemini import GeminiVisionClient

_MAX_MESSAGE_LEN = 40  # 컬럼 한도(200)보다 훨씬 짧게 — 프롬프트가 15자를 요구하지만 안전판
_TEMPLATE_LEVELUP = "우와! 나 더 컸어!"


async def get_or_create_levelup_message(
    session: AsyncSession, stage_index: int, stage_name: str, *, client: GeminiVisionClient | None = None
) -> tuple[str, str]:
    """이 stage_index에 대한 레벨업 대사를 (문장, source) 형태로 돌려준다.
    전역 캐시가 있으면 AI를 아예 안 부르고 그대로 반환한다(source는 "ai"|"template")."""
    existing = (
        await session.execute(
            select(PetStageMessage).where(PetStageMessage.stage_index == stage_index)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.message, existing.source

    client = client or GeminiVisionClient()
    try:
        ai_text = await client.generate_pet_levelup_line(stage_name)
    except Exception:  # noqa: BLE001 - AI 실패가 레벨업 축하 자체를 막으면 안 됨
        ai_text = None

    if ai_text:
        text, source = ai_text[:_MAX_MESSAGE_LEN], "ai"
    else:
        text, source = _TEMPLATE_LEVELUP, "template"

    session.add(PetStageMessage(stage_index=stage_index, message=text, source=source))
    try:
        await session.commit()
    except IntegrityError:
        # 동시 요청 레이스(같은 단계에 동시에 처음 도달한 두 사용자) — 이미 다른
        # 요청이 이 단계의 캐시를 만들었으면 그걸 그대로 읽는다(user_digest/
        # price_discovery와 같은 패턴).
        await session.rollback()
        winner = (
            await session.execute(
                select(PetStageMessage).where(PetStageMessage.stage_index == stage_index)
            )
        ).scalar_one()
        return winner.message, winner.source

    return text, source
