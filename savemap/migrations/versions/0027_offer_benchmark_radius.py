"""add offer.benchmark_radius_km
(실측 비교 반경 사다리 — 3km에서 이웃이 모자라면 10km까지 넓혀 잡는다)

왜 저장까지 하는가: 절약률은 검색 시점에 재계산되지 않고 오퍼에 굳혀 저장된다.
그래서 "이 오퍼의 비교 기준이 3km 안에서 나온 것인지, 10km까지 넓혀서 나온
것인지"를 나중에 알 방법이 계산 당시 값을 남겨두는 것뿐이다. 이걸 모르면 10km
밖 매장 가격과 비교해놓고 화면에는 "주변 매장 실측가"라고 쓰게 된다.

구 데이터는 NULL로 남고, 그 경우 화면 문구는 기존 "주변"을 그대로 쓴다
(savings_report.region_scope_label) — 재동기화가 돌면 실제 반경으로 채워진다.

Revision ID: 0027_offer_benchmark_radius
Revises: 0026_pet_stage_message
Create Date: 2026-09-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0027_offer_benchmark_radius"
down_revision = "0026_pet_stage_message"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("offer", sa.Column("benchmark_radius_km", sa.Numeric(5, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("offer", "benchmark_radius_km")
