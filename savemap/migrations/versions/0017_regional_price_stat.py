"""add regional_price_stat (한국소비자원 참가격 외식비 시도별 평균가)

주변에 비교할 매장이 없을 때 그동안 Gemini 추정 통상가로 절약률을 계산했다 — 앱이
보여주는 "얼마 아꼈다"의 근거가 AI 추측이었다는 뜻이다. 그 자리를 정부가 매달 조사해
공표하는 통계로 바꾸기 위한 테이블. 비교 우선순위는 실측 > 정부 통계 > AI 추정.

Revision ID: 0017_regional_price_stat
Revises: 0016_menu_item_normalized_name
Create Date: 2026-08-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_regional_price_stat"
down_revision = "0016_menu_item_normalized_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regional_price_stat",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dish", sa.String(length=64), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("survey_period", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("dish", "region", name="uq_regional_price_dish_region"),
    )
    op.create_index("ix_regional_price_dish_region", "regional_price_stat", ["dish", "region"])


def downgrade() -> None:
    op.drop_index("ix_regional_price_dish_region", table_name="regional_price_stat")
    op.drop_table("regional_price_stat")
