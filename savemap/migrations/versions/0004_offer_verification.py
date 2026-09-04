"""add offer_verification (MAP 카드 단위 "아직 있어요/없어졌어요" 신뢰도 검증)

Revision ID: 0004_offer_verification
Revises: 0003_savings_certification_asset
Create Date: 2026-07-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_offer_verification"
down_revision = "0003_savings_certification_asset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # XP 지급 사유 추가 (절약 인증 시 XP 지급). 기존 값은 그대로 둔다.
    op.execute("ALTER TYPE xp_reason ADD VALUE IF NOT EXISTS 'SAVINGS_CERTIFIED'")

    verdict_type = postgresql.ENUM("AVAILABLE", "SOLD_OUT", name="verdict_type", create_type=False)

    op.create_table(
        "offer_verification",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offer.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("verdict", verdict_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_offer_verification_offer_id", "offer_verification", ["offer_id"])


def downgrade() -> None:
    op.drop_index("ix_offer_verification_offer_id", table_name="offer_verification")
    op.drop_table("offer_verification")
