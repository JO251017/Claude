"""add offer.menu_item_id (메뉴 가격 비교로 자동 생성되는 오퍼 추적용)

Revision ID: 0006_offer_menu_item_link
Revises: 0005_menu_price_visit
Create Date: 2026-07-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_offer_menu_item_link"
down_revision = "0005_menu_price_visit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "offer",
        sa.Column(
            "menu_item_id",
            sa.Integer(),
            sa.ForeignKey("menu_item.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_offer_menu_item_id", "offer", ["menu_item_id"])


def downgrade() -> None:
    op.drop_index("ix_offer_menu_item_id", table_name="offer")
    op.drop_column("offer", "menu_item_id")
