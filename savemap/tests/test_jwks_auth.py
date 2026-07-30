import asyncio
import base64
from unittest.mock import AsyncMock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwt

from app.api.deps import require_user_id
from app.core.security import decode_supabase_jwt

KID = "test-kid-1"


def _b64url(n: int, length: int = 32) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()


def _make_es256_token_and_jwks(sub: str = "user-es256"):
    """실제 배포본에서 발견된 것과 같은 ES256(비대칭 서명) 토큰 + 대응하는 JWKS를 만든다."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    numbers = private_key.public_key().public_numbers()
    jwk_dict = {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(numbers.x),
        "y": _b64url(numbers.y),
        "kid": KID,
        "alg": "ES256",
        "use": "sig",
    }

    token = jwt.encode(
        {"sub": sub, "aud": "authenticated"},
        pem_private,
        algorithm="ES256",
        headers={"kid": KID},
    )
    return token, [jwk_dict]


def test_decode_es256_token_via_jwks():
    """예전엔 HS256만 지원해서 이 요청이 항상 401로 거부되고 있었다 — 이 테스트는 그 회귀를 막는다."""
    token, jwks = _make_es256_token_and_jwks()
    with patch("app.core.security._get_jwks", new=AsyncMock(return_value=jwks)):
        claims = asyncio.run(decode_supabase_jwt(token))
    assert claims["sub"] == "user-es256"


def test_require_user_id_accepts_es256_token():
    token, jwks = _make_es256_token_and_jwks(sub="merchant-1")
    with patch("app.core.security._get_jwks", new=AsyncMock(return_value=jwks)):
        result = asyncio.run(require_user_id(f"Bearer {token}"))
    assert result == "merchant-1"


def test_decode_es256_token_with_unknown_kid_raises():
    token, _ = _make_es256_token_and_jwks()
    with patch("app.core.security._get_jwks", new=AsyncMock(return_value=[])):
        try:
            asyncio.run(decode_supabase_jwt(token))
            assert False, "unknown kid는 실패해야 함"
        except ValueError:
            pass
