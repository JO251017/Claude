"""add menu_item, store_status_update, store_interest (음식점/카페 가격 비교 + GPS 방문 인증)

Revision ID: 0005_menu_price_visit
Revises: 0004_offer_verification
Create Date: 2026-07-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_menu_price_visit"
down_revision = "0004_offer_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 방문 상태 업데이트 / 영수증 인증 XP 사유 추가
    op.execute("ALTER TYPE xp_reason ADD VALUE IF NOT EXISTS 'STORE_VISIT_UPDATE'")
    op.execute("ALTER TYPE xp_reason ADD VALUE IF NOT EXISTS 'RECEIPT_VERIFIED'")

    source_type = postgresql.ENUM(
        "S1_PUBLIC", "S2_PARTNER", "S3_MERCHANT", "S4_REPORT", "S5_VERIFICATION",
        name="source_type", create_type=False,
    )

    op.create_table(
        "menu_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("source", source_type, nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_menu_item_place_id", "menu_item", ["place_id"])
    op.create_index("ix_menu_item_name", "menu_item", ["name"])

    op.create_table(
        "store_status_update",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Enum("OPEN", "CLOSED", "TEMP_CLOSED", "UNKNOWN", name="business_status"), nullable=False),
        sa.Column("lat", sa.Numeric(9, 6), nullable=False),
        sa.Column("lng", sa.Numeric(9, 6), nullable=False),
        sa.Column("distance_m", sa.Numeric(8, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_store_status_update_place_id", "store_status_update", ["place_id"])

    op.create_table(
        "store_interest",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="CASCADE"), nullable=False),
        sa.Column("first_interested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_interested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "place_id", name="uq_store_interest_user_place"),
    )
    op.create_index("ix_store_interest_place_id", "store_interest", ["place_id"])


def downgrade() -> None:
    op.drop_index("ix_store_interest_place_id", table_name="store_interest")
    op.drop_table("store_interest")
    op.drop_index("ix_store_status_update_place_id", table_name="store_status_update")
    op.drop_table("store_status_update")
    op.drop_index("ix_menu_item_name", table_name="menu_item")
    op.drop_index("ix_menu_item_place_id", table_name="menu_item")
    op.drop_table("menu_item")
    op.execute("DROP TYPE IF EXISTS business_status")
