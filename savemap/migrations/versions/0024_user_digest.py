"""create user_digest table
(AI 활용 확대 안건 C — 개인화 절약 다이제스트 캐시)

MY탭의 "이번 주 OO에서 제일 아꼈어요" 같은 개인화 요약을 매 요청마다 AI로
새로 만들지 않고, 사용자당 주(week_start) 1번만 생성해 여기 캐시한다 —
검색 응답의 report.one_line(savings_report.py)이 매 요청마다 LLM을 안 부르는
것과 같은 이유. (user_id, week_start) 부분이 아니라 전체 유니크 인덱스로
동시 요청 레이스를 DB 레벨에서 막는다.

Revision ID: 0024_user_digest
Revises: 0023_offer_ai_one_line
Create Date: 2026-08-31
"""
import sqlalchemy as sa
from alembic import op

revision = "0024_user_digest"
down_revision = "0023_offer_ai_one_line"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_digest",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("week_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_text", sa.String(length=300), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
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
        "ux_user_digest_user_week", "user_digest", ["user_id", "week_start"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ux_user_digest_user_week", table_name="user_digest")
    op.drop_table("user_digest")
