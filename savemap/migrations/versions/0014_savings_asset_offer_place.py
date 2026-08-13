"""add savings_asset.offer_id/place_id/place_name (EXCHANGE 재도입 — 오퍼 상세
"저장하기"로 만든 자산과 기존 자유입력 자산을 같은 테이블에서 구분)

Revision ID: 0014_savings_asset_offer_place
Revises: 0013_merchant_verification
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_savings_asset_offer_place"
down_revision = "0013_merchant_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "savings_asset",
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offer.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "savings_asset",
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "savings_asset",
        sa.Column("place_name", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_savings_asset_place_id", "savings_asset", ["place_id"])


def downgrade() -> None:
    op.drop_index("ix_savings_asset_place_id", table_name="savings_asset")
    op.drop_column("savings_asset", "place_name")
    op.drop_column("savings_asset", "place_id")
    op.drop_column("savings_asset", "offer_id")
