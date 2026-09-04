"""add savings_certification and savings_asset (리디자인: 실제 절약 기반 성장 + EXCHANGE)

Revision ID: 0003_savings_certification_asset
Revises: 0002_place_owner
Create Date: 2026-07-29
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_savings_certification_asset"
down_revision = "0002_place_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "savings_certification",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offer.id", ondelete="SET NULL"), nullable=True),
        sa.Column("place_name", sa.String(length=255), nullable=False),
        sa.Column("base_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("actual_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "method",
            sa.Enum("SIMPLE", "RECEIPT", name="certification_method"),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Enum("HIGH", "MEDIUM", "LOW", name="certification_confidence"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_savings_certification_user_id", "savings_certification", ["user_id"])

    op.create_table(
        "savings_asset",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("condition_text", sa.String(length=500), nullable=True),
        sa.Column("estimated_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("AVAILABLE", "EXCHANGED", name="asset_status"),
            nullable=False,
            server_default="AVAILABLE",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_savings_asset_owner_user_id", "savings_asset", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_savings_asset_owner_user_id", table_name="savings_asset")
    op.drop_table("savings_asset")
    op.drop_index("ix_savings_certification_user_id", table_name="savings_certification")
    op.drop_table("savings_certification")
    op.execute("DROP TYPE IF EXISTS certification_method")
    op.execute("DROP TYPE IF EXISTS certification_confidence")
    op.execute("DROP TYPE IF EXISTS asset_status")
