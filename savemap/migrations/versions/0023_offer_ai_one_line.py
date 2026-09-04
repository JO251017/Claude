"""add offer.ai_one_line / ai_one_line_generated_at
(AI 활용 확대 안건 D — 매장 카드 AI 한 줄 소개 캐시)

검색 응답의 report.one_line은 지금까지 savings_report.py가 매 요청마다
결정론적 템플릿 문자열 몇 종류만 돌려썼다(그 자체는 그대로 유지 — 빠르고
비용이 안 들고 문구가 안정적이라는 장점이 있다). 이 컬럼은 그 문구를 관리자
배치가 미리 한 번만 AI로 다듬어 캐시하는 자리다 — 값이 있으면 검색 응답이
그대로 쓰고, 없으면(아직 생성 안 됨) 기존 템플릿으로 폴백한다. AI가 새
숫자/사실을 지어내면 그 결과를 저장하지 않으므로(app/engine/ai_text_guard.py
검증) 이 컬럼에 들어있는 값은 항상 실제 데이터에서만 나온 문장이다.

Revision ID: 0023_offer_ai_one_line
Revises: 0022_price_discovery
Create Date: 2026-08-31
"""
import sqlalchemy as sa
from alembic import op

revision = "0023_offer_ai_one_line"
down_revision = "0022_price_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("offer", sa.Column("ai_one_line", sa.String(length=200), nullable=True))
    op.add_column(
        "offer", sa.Column("ai_one_line_generated_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("offer", "ai_one_line_generated_at")
    op.drop_column("offer", "ai_one_line")
