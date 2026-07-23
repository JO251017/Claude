from jose import JWTError, jwt

from app.core.config import settings


def decode_supabase_jwt(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError as exc:
        raise ValueError("invalid token") from exc


class PartnerOAuthTokenProvider:
    def __init__(self, partner: str):
        self.partner = partner

    async def get_token(self) -> str:
        raise NotImplementedError(
            f"{self.partner} OAuth2 토큰 발급은 실제 파트너 스펙 확인 후 구현 (미확인)"
        )
