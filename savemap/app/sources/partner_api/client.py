from app.core.security import PartnerOAuthTokenProvider
from app.sources.partner_api.circuit_breaker import CircuitBreaker


class PartnerApiClient:
    def __init__(self, partner: str):
        self.partner = partner
        self.token_provider = PartnerOAuthTokenProvider(partner)
        self.breaker = CircuitBreaker()

    async def fetch_benefits(self) -> list[dict]:
        self.breaker.before_call()
        raise NotImplementedError(
            f"{self.partner} 혜택 API(마이데이터/멤버십) 스펙 확인 후 구현 (미확인). "
            "마이데이터는 원본 저장 금지 — 파생 지표만 추출한다."
        )
