"""add franchise_brand.suggested_match_keywords
(AI 매칭 키워드 제안 — match_keywords와 별개, 실제 매칭엔 안 쓰임)

Revision ID: 0029_franchise_sugg_keywords
Revises: 0028_menu_synonym_candidate
Create Date: 2026-09-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0029_franchise_sugg_keywords"
down_revision = "0028_menu_synonym_candidate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "franchise_brand", sa.Column("suggested_match_keywords", sa.String(length=512), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("franchise_brand", "suggested_match_keywords")
