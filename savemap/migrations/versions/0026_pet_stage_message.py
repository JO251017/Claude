"""create pet_stage_message table
(AI MVP §D — 펫 레벨업 축하 대사 전역 캐시)

사용자별이 아니라 성장 단계(stage_index)당 전역으로 하나만 캐시한다 —
user_digest(주 단위, 사용자별)와 달리 이 대사는 순수 축하 문구라 사용자마다
달라질 이유가 없다. 앱 전체 수명 동안 이 기능의 Gemini 호출 횟수를 최대
"성장 단계 개수"번으로 못박기 위한 설계.

Revision ID: 0026_pet_stage_message
Revises: 0025_place_visit_and_growth
Create Date: 2026-09-01
"""
import sqlalchemy as sa
from alembic import op

revision = "0026_pet_stage_message"
down_revision = "0025_place_visit_and_growth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pet_stage_message",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage_index", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(length=200), nullable=False),
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
        "ix_pet_stage_message_stage_index", "pet_stage_message", ["stage_index"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_pet_stage_message_stage_index", table_name="pet_stage_message")
    op.drop_table("pet_stage_message")
