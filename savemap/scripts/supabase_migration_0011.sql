-- SaveMap: 메뉴판 사진 제보 XP 보상용 xp_reason 값 추가
-- (새 메뉴 정보를 더했을 때만 +10 XP — 같은 메뉴 반복 제보로는 지급 안 됨)
--
-- ⚠️ 1단계와 2단계를 반드시 "따로" 실행하세요 (한 번에 돌리면 55P04 에러).
-- Postgres는 같은 트랜잭션 안에서 방금 추가한 enum 값을 조회/사용할 수 없습니다.

-- ── 1단계: 이것만 먼저 실행 ─────────────────────────────
ALTER TYPE xp_reason ADD VALUE IF NOT EXISTS 'MENU_REPORT';

UPDATE public.alembic_version SET version_num = '0011_menu_report_xp' WHERE version_num = '0010_place_recommendation';

-- ── 2단계: 1단계 완료 후, 아래 줄만 따로 선택해서 실행 ──
-- (MENU_REPORT가 목록에 보이면 정상)
-- SELECT unnest(enum_range(NULL::xp_reason)) AS xp_reason_values;
