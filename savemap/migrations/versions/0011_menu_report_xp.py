"""add xp_reason MENU_REPORT (메뉴판 사진 제보 보상 - 새 메뉴 정보일 때만 지급)

Revision ID: 0011_menu_report_xp
Revises: 0010_place_recommendation
Create Date: 2026-07-31
"""
from alembic import op

revision = "0011_menu_report_xp"
down_revision = "0010_place_recommendation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE xp_reason ADD VALUE IF NOT EXISTS 'MENU_REPORT'")


def downgrade() -> None:
    # Postgres enum 값 제거는 지원되지 않음 — 남겨둬도 무해하다.
    pass
