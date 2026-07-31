"""add place_recommendation + place.category_name (AI 절약 리포트 근거/업종 표시)

Revision ID: 0010_place_recommendation
Revises: 0009_savings_cert_place_id
Create Date: 2026-07-31
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_place_recommendation"
down_revision = "0009_savings_cert_place_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("place", sa.Column("category_name", sa.String(length=255), nullable=True))
    op.create_table(
        "place_recommendation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "place_id", name="uq_place_recommendation_user_place"),
    )
    op.create_index("ix_place_recommendation_place_id", "place_recommendation", ["place_id"])


def downgrade() -> None:
    op.drop_index("ix_place_recommendation_place_id", table_name="place_recommendation")
    op.drop_table("place_recommendation")
    op.drop_column("place", "category_name")
