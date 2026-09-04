"""방문 GPS 인증(place_visit) + 성장 이벤트 기록(xp_ledger.place_id) +
좌표 출처(place.location_source)

(2026-09-01, 사용자 확정 "방문 GPS 인증 공식 기준" + 펫 성장치 재조정)

- place_visit: 거리 50m·GPS 정확도 30m·서로 다른 시점 2회 연속 측정·서버
  재검증까지 전부 통과한 확정 방문만 남긴다. (user_id, place_id, visit_date)
  유니크 인덱스가 "하루 1회" 제한의 최종 방어선(동시 요청도 여기서 막힘).
- xp_ledger.place_id: 기존 xp_ledger(user_id/delta/reason/created_at)에 place_id
  하나만 얹어 "성장 이벤트 기록"으로 쓴다 — 새 이벤트 테이블을 따로 만들지 않음.
- place.location_source: 좌표 출처 기록용(출입구 좌표 시스템은 범위 밖, 기록만).
- xp_reason에 PLACE_VISIT/PLACE_RECOMMEND 추가 — 방문 기록과 추천이 새로
  XP를 받는다(추천은 지금까지 XP가 전혀 없었음).

Revision ID: 0025_place_visit_and_growth
Revises: 0024_user_digest
Create Date: 2026-09-01
"""
import sqlalchemy as sa
from alembic import op

revision = "0025_place_visit_and_growth"
down_revision = "0024_user_digest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE xp_reason ADD VALUE IF NOT EXISTS 'PLACE_VISIT'")
    op.execute("ALTER TYPE xp_reason ADD VALUE IF NOT EXISTS 'PLACE_RECOMMEND'")

    op.add_column("xp_ledger", sa.Column("place_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_xp_ledger_place_id", "xp_ledger", "place", ["place_id"], ["id"], ondelete="SET NULL"
    )

    op.add_column("place", sa.Column("location_source", sa.String(length=32), nullable=True))

    op.create_table(
        "place_visit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column(
            "place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("lat", sa.Numeric(9, 6), nullable=False),
        sa.Column("lng", sa.Numeric(9, 6), nullable=False),
        sa.Column("gps_accuracy", sa.Numeric(6, 2), nullable=False),
        sa.Column("distance_at_visit", sa.Numeric(8, 2), nullable=False),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("client_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_place_visit_user_place_date",
        "place_visit",
        ["user_id", "place_id", "visit_date"],
        unique=True,
    )
    op.create_index("ix_place_visit_user_id", "place_visit", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_place_visit_user_id", table_name="place_visit")
    op.drop_index("uq_place_visit_user_place_date", table_name="place_visit")
    op.drop_table("place_visit")
    op.drop_column("place", "location_source")
    op.drop_constraint("fk_xp_ledger_place_id", "xp_ledger", type_="foreignkey")
    op.drop_column("xp_ledger", "place_id")
    # Postgres enum 값 제거는 지원되지 않음 — 남겨둬도 무해하다.
