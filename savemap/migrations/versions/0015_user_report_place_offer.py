"""add user_report.place_id/offer_id (제보 → 실제 Place/Offer 게시 연결 — 예전엔
PENDING으로 저장만 되고 지도에 반영하는 코드가 없어서 완전히 끊긴 기능이었다)

Revision ID: 0015_user_report_place_offer
Revises: 0014_savings_asset_offer_place
Create Date: 2026-08-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_user_report_place_offer"
down_revision = "0014_savings_asset_offer_place"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_report",
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "user_report",
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offer.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_user_report_place_id", "user_report", ["place_id"])


def downgrade() -> None:
    op.drop_index("ix_user_report_place_id", table_name="user_report")
    op.drop_column("user_report", "offer_id")
    op.drop_column("user_report", "place_id")
