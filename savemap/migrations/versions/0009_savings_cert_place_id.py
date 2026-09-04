"""add savings_certification.place_id (매장별 식사 인증 횟수 집계용)

Revision ID: 0009_savings_cert_place_id
Revises: 0008_menu_item_ai_typical_price
Create Date: 2026-07-31
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_savings_cert_place_id"
down_revision = "0008_menu_item_ai_typical_price"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "savings_certification",
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index(
        "ix_savings_certification_place_id", "savings_certification", ["place_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_savings_certification_place_id", table_name="savings_certification")
    op.drop_column("savings_certification", "place_id")
