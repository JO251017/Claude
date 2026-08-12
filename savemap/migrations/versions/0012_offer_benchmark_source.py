"""add offer.benchmark_source (절약액을 무엇과 비교해 계산했는지: region/ai/None)

Revision ID: 0012_offer_benchmark_source
Revises: 0011_menu_report_xp
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_offer_benchmark_source"
down_revision = "0011_menu_report_xp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("offer", sa.Column("benchmark_source", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("offer", "benchmark_source")
