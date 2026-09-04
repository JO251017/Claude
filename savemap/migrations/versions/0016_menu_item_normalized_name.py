"""add menu_item.normalized_name (지역 실측 비교가 표기 차이 때문에 거의 안 걸리던 문제)

예전 비교 조건은 메뉴명 완전 일치라, "아메리카노"와 "아메리카노(ICE)"가 다른 메뉴로
갈렸다. 착한가격업소에서 들어온 실제 가격이 1만 건 넘게 쌓여 있어도 서로 비교가 안 돼
대부분 AI 추정 통상가로 떨어지고 있었다(2026-08-20 확인). 정규화된 이름을 따로 저장하고
그걸로 매칭한다.

Revision ID: 0016_menu_item_normalized_name
Revises: 0015_user_report_place_offer
Create Date: 2026-08-20
"""
import sqlalchemy as sa
from alembic import op

from app.engine.menu_name import normalize_menu_name

revision = "0016_menu_item_normalized_name"
down_revision = "0015_user_report_place_offer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "menu_item",
        sa.Column("normalized_name", sa.String(length=255), nullable=False, server_default=""),
    )

    # 기존 행 백필. 정규화 규칙이 파이썬 쪽에만 있어서(괄호 제거·크기 접미사 처리 등
    # SQL로 옮기면 두 벌 관리가 된다) 값을 읽어와 계산한 뒤 되쓴다. 같은 정규화 결과가
    # 반복되는 경우가 많으므로 이름 단위로 묶어 UPDATE 횟수를 줄인다.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT DISTINCT name FROM menu_item")).fetchall()
    for (name,) in rows:
        bind.execute(
            sa.text("UPDATE menu_item SET normalized_name = :norm WHERE name = :name"),
            {"norm": normalize_menu_name(name or "")[:255], "name": name},
        )

    op.create_index("ix_menu_item_normalized_name", "menu_item", ["normalized_name"])
    # 서버 기본값은 백필 동안만 필요했다 — 이후 삽입은 모델의 @validates가 채운다.
    op.alter_column("menu_item", "normalized_name", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_menu_item_normalized_name", table_name="menu_item")
    op.drop_column("menu_item", "normalized_name")
