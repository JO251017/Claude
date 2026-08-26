"""add place.accepts_local_currency / place.local_currency_verified_at

전국지역화폐가맹점표준데이터(data.go.kr/data/15100062) 매칭 결과를 담을 컬럼.
PaymentMethodType.LOCAL_CURRENCY는 지금 PaymentMethodDerived(유저×수단 자기신고)
뿐이라 그 매장이 실제로 지역화폐 가맹점인지 검증할 방법이 없었다 — 이 컬럼은
매장 자체의 사실(지자체 공식 명단에 있는지)이라 사용자별이 아니라 Place에 직접
둔다. 가격/할인율은 이 데이터에 없어 만들어내지 않고(benefit_combiner에 엮지
않음), 검색 결과에 정보성 배지로만 노출한다.

Revision ID: 0020_place_local_currency
Revises: 0019_offer_benchmark_metadata
Create Date: 2026-08-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0020_place_local_currency"
down_revision = "0019_offer_benchmark_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "place",
        sa.Column("accepts_local_currency", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "place", sa.Column("local_currency_verified_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("place", "local_currency_verified_at")
    op.drop_column("place", "accepts_local_currency")
