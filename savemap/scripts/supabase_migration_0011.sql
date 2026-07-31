-- SaveMap: 메뉴판 사진 제보 XP 보상용 xp_reason 값 추가
-- (새 메뉴 정보를 더했을 때만 +10 XP — 같은 메뉴 반복 제보로는 지급 안 됨)
-- Supabase SQL Editor에서 그대로 실행하세요. (재실행해도 안전)

ALTER TYPE xp_reason ADD VALUE IF NOT EXISTS 'MENU_REPORT';

UPDATE public.alembic_version SET version_num = '0011_menu_report_xp' WHERE version_num = '0010_place_recommendation';

-- 확인 (MENU_REPORT가 목록에 있으면 정상)
SELECT unnest(enum_range(NULL::xp_reason)) AS xp_reason_values;
