"""AI Price Discovery Engine — source_type 확장 + price_discovery_job 큐

"AI Price Discovery Engine" 지시서(2026-08-31): 가격 없는 매장을 AI(Gemini 검색
그라운딩)로 조사해 공개 자료에서 실제 가격을 찾는다. 발견된 가격 자체는 새
테이블을 만들지 않고 기존 price_history/offer_sync 파이프라인을 그대로 태운다
(28-33 "이미 동일 목적 테이블 있으면 확장" 원칙) — 이 마이그레이션은 (1) 그
출처를 구분할 SourceType 값 2개 추가, (2) 조사 작업 큐 테이블 1개만 새로 만든다.

Revision ID: 0022_price_discovery
Revises: 0021_price_history
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_price_discovery"
down_revision = "0021_price_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE는 트랜잭션 내에서 안전하게 실행되고(PG12+), 이
    # 마이그레이션은 새 값을 바로 사용(INSERT)하지 않으므로 트랜잭션 제약과
    # 무관하다. 값은 SourceType 멤버의 .value(소문자)가 아니라 .name(대문자)이다 —
    # 이 저장소의 SAEnum(PyEnum) 컬럼은 전부 .name을 DB 라벨로 쓴다(0005의
    # xp_reason ADD VALUE 'STORE_VISIT_UPDATE'와 동일 관례, `SAEnum(SourceType,
    # name="source_type").enums`로 직접 확인함).
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'S6_AI_DISCOVERY_OFFICIAL'")
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'S6_AI_DISCOVERY_WEB'")

    discovery_job_status = postgresql.ENUM(
        "PENDING", "PROCESSING", "COMPLETED", "FAILED", "MANUAL_REVIEW",
        name="discovery_job_status",
    )
    discovery_job_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "price_discovery_job",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING", "PROCESSING", "COMPLETED", "FAILED", "MANUAL_REVIEW",
                name="discovery_job_status", create_type=False,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("result_summary", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_price_discovery_job_place_id", "price_discovery_job", ["place_id"])
    op.create_index(
        "ix_price_discovery_job_status_priority", "price_discovery_job", ["status", "priority"]
    )
    # 동일 매장에 pending/processing 작업이 동시에 여럿 생기지 않도록 DB 레벨에서
    # 막는다(지시서 28-19, "애플리케이션에서만 중복 방지하지 않는다") — 부분
    # 유니크 인덱스라 completed/failed/manual_review 상태는 여러 건 남아도 된다
    # (매장 하나를 여러 번 조사한 이력은 남아야 한다).
    op.execute(
        "CREATE UNIQUE INDEX ux_price_discovery_job_active_place "
        "ON price_discovery_job (place_id) "
        "WHERE status IN ('PENDING', 'PROCESSING')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_price_discovery_job_active_place")
    op.drop_index("ix_price_discovery_job_status_priority", table_name="price_discovery_job")
    op.drop_index("ix_price_discovery_job_place_id", table_name="price_discovery_job")
    op.drop_table("price_discovery_job")
    op.execute("DROP TYPE IF EXISTS discovery_job_status")
    # source_type에 추가한 enum 값은 PostgreSQL이 삭제를 지원하지 않아 되돌리지 않는다.
