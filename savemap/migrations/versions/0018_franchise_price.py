"""add franchise_brand / franchise_price (본사 공식 가격표 → 상호명 매칭으로 매장 가격 채우기)

인허가 데이터로 들어온 매장 수만 건은 이름·주소만 있고 가격이 비어 있다. 체인점은 본사가
공식 가격을 공개하고 전국이 대체로 같은 값이라, 브랜드 가격표 한 벌로 수천 곳을 채울 수
있다. 가격은 관리자가 올린 값만 저장한다 — 서버가 가격을 만들어내지 않는다.

Revision ID: 0018_franchise_price
Revises: 0017_regional_price_stat
Create Date: 2026-08-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0018_franchise_price"
down_revision = "0017_regional_price_stat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "franchise_brand",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("match_keywords", sa.String(length=512), nullable=True),
        sa.Column("official_url", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "franchise_price",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "brand_id",
            sa.Integer(),
            sa.ForeignKey("franchise_brand.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_item_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("effective_period", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("brand_id", "normalized_item_name", name="uq_franchise_price_item"),
    )
    op.create_index("ix_franchise_price_brand_id", "franchise_price", ["brand_id"])


def downgrade() -> None:
    op.drop_index("ix_franchise_price_brand_id", table_name="franchise_price")
    op.drop_table("franchise_price")
    op.drop_table("franchise_brand")
