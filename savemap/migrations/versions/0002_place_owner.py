"""add place.owner_user_id for merchant console ownership

Revision ID: 0002_place_owner
Revises: 0001_initial
Create Date: 2026-07-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_place_owner"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("place", sa.Column("owner_user_id", sa.String(length=64), nullable=True))
    op.create_index("ix_place_owner_user_id", "place", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_place_owner_user_id", table_name="place")
    op.drop_column("place", "owner_user_id")
