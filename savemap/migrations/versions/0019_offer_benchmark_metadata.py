"""add offer.menu_item_id index + benchmark_sample_count/benchmark_synced_at
(재동기화 배치의 전제 — 벤치마크가 적재 시점에 굳는 문제를 고치기 전 준비)

절약 계산(price_comparison.compare_menu_item)은 메뉴 적재/갱신 시점에만 돌고 결과가
Offer 컬럼으로 굳는다. 나중에 주변에 매장이 새로 생기거나 정부 통계·프랜차이즈
가격이 채워져도 이미 만들어진 Offer는 재계산 전까지 그대로다 — 재동기화 배치가
필요한데, 그 배치가 매 호출마다 menu_item_id로 Offer를 찾으므로(sync_menu_offer)
인덱스가 없으면 수만 건에서 건당 풀스캔이 난다.

benchmark_sample_count/benchmark_synced_at은 "이웃 2곳"과 "이웃 30곳"을 구분하고
"마지막으로 언제 재계산했는지"를 알기 위해 필요하다 — 값이 안 바뀌면 SQLAlchemy가
UPDATE를 안 내서 updated_at으로는 "오래된 것만 재동기화"가 불가능하다.

Revision ID: 0019_offer_benchmark_metadata
Revises: 0018_franchise_price
Create Date: 2026-08-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0019_offer_benchmark_metadata"
down_revision = "0018_franchise_price"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_offer_menu_item_id", "offer", ["menu_item_id"])
    op.add_column("offer", sa.Column("benchmark_sample_count", sa.Integer(), nullable=True))
    op.add_column(
        "offer", sa.Column("benchmark_synced_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("offer", "benchmark_synced_at")
    op.drop_column("offer", "benchmark_sample_count")
    op.drop_index("ix_offer_menu_item_id", table_name="offer")
