"""add merchant_verification (사업자 콘솔 접근 제어 최소 기능)

Revision ID: 0013_merchant_verification
Revises: 0012_offer_benchmark_source
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_merchant_verification"
down_revision = "0012_offer_benchmark_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "merchant_verification",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", name="uq_merchant_verification_user"),
    )


def downgrade() -> None:
    op.drop_table("merchant_verification")
