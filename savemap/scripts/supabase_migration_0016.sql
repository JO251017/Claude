-- SaveMap: menu_item에 normalized_name 추가 (지역 실측 가격 비교가 표기 차이 때문에
-- 거의 안 걸리던 문제 — "아메리카노"와 "아메리카노(ICE)"가 다른 메뉴로 취급됐음)
-- Supabase SQL Editor에서 그대로 실행하세요. (재실행해도 안전)
--
-- 주의: 이 SQL은 컬럼만 만든다. 기존 행의 실제 값 채우기(백필)는 정규화 규칙이
-- 파이썬 코드에만 있어서 SQL로는 못 한다 — 이 SQL 실행 후, 배포된 서버에 아래
-- 관리자 API를 한 번 호출해야 한다(사장님용 안내 스크립트를 따로 보냄):
--   POST /v1/admin/maintenance/backfill-menu-normalized-names

ALTER TABLE public.menu_item
    ADD COLUMN IF NOT EXISTS normalized_name varchar(255) NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS ix_menu_item_normalized_name ON public.menu_item (normalized_name);

UPDATE public.alembic_version SET version_num = '0016_menu_item_normalized_name' WHERE version_num = '0015_user_report_place_offer';

-- 확인
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'menu_item' AND column_name = 'normalized_name';
