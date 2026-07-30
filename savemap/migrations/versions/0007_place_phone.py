"""add place.phone (매장 전화번호 - 카카오 실데이터 또는 사장님 직접 입력)

Revision ID: 0007_place_phone
Revises: 0006_offer_menu_item_link
Create Date: 2026-07-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_place_phone"
down_revision = "0006_offer_menu_item_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("place", sa.Column("phone", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("place", "phone")
