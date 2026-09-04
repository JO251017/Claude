"""create menu_synonym_candidate table
(AI 동의어 후보 — 사람이 검토하기 전까지 실제 정규화 규칙에는 반영되지 않는다)

Revision ID: 0028_menu_synonym_candidate
Revises: 0027_offer_benchmark_radius
Create Date: 2026-09-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0028_menu_synonym_candidate"
down_revision = "0027_offer_benchmark_radius"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "menu_synonym_candidate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("variant", sa.String(length=64), nullable=False),
        sa.Column("canonical", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("variant_places", sa.Integer(), nullable=True),
        sa.Column("canonical_places", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("variant", "canonical", name="uq_menu_synonym_candidate_pair"),
    )
    op.create_index(
        "ix_menu_synonym_candidate_status", "menu_synonym_candidate", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_menu_synonym_candidate_status", table_name="menu_synonym_candidate")
    op.drop_table("menu_synonym_candidate")
