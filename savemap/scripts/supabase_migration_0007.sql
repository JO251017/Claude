-- SaveMap: 매장 전화번호 컬럼 추가 (카카오 실데이터 또는 사장님 직접 입력 - 지어내지 않음)
-- Supabase SQL Editor에서 그대로 실행하세요. (재실행해도 안전)

ALTER TABLE public.place ADD COLUMN IF NOT EXISTS phone character varying(32);

UPDATE public.alembic_version SET version_num = '0007_place_phone' WHERE version_num = '0006_offer_menu_item_link';

-- 확인
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'place' AND column_name = 'phone';
