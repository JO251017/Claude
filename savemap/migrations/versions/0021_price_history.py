"""add price_history table

가격이 바뀔 때 기존 값을 덮어쓰기만 하고 이력이 사라지던 문제를 고친다
("SaveMap vNext 구현 지시서" 2026-08-31, "3. 가격 이력 관리"). MenuItem.price를
바꾸는 모든 저장 경로(app/engine/offer_sync.py:sync_menu_offer를 거침)가 가격이
실제로 바뀔 때만 이 테이블에 이전 행을 닫고(valid_to/is_current=False) 새 행을
추가한다.

Revision ID: 0021_price_history
Revises: 0020_place_local_currency
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_price_history"
down_revision = "0020_place_local_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    source_type = postgresql.ENUM(
        "S1_PUBLIC", "S2_PARTNER", "S3_MERCHANT", "S4_REPORT", "S5_VERIFICATION",
        name="source_type", create_type=False,
    )

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "menu_item_id", sa.Integer(), sa.ForeignKey("menu_item.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_text", sa.String(length=500), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_price_history_menu_item_id", "price_history", ["menu_item_id"])
    op.create_index(
        "ix_price_history_menu_item_current", "price_history", ["menu_item_id", "is_current"]
    )


def downgrade() -> None:
    op.drop_index("ix_price_history_menu_item_current", table_name="price_history")
    op.drop_index("ix_price_history_menu_item_id", table_name="price_history")
    op.drop_table("price_history")
