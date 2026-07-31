"""add menu_item.ai_typical_price (비교 표본 부족 시 참고용 Gemini 추정 시세 캐시)

Revision ID: 0008_menu_item_ai_typical_price
Revises: 0007_place_phone
Create Date: 2026-07-31
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_menu_item_ai_typical_price"
down_revision = "0007_place_phone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("menu_item", sa.Column("ai_typical_price", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("menu_item", "ai_typical_price")
