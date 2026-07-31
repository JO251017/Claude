-- SaveMap: 메뉴 비교 표본 부족 시 참고용 AI 추정 시세 컬럼 추가 (절약률/XP 계산에는 안 씀)
-- Supabase SQL Editor에서 그대로 실행하세요. (재실행해도 안전)

ALTER TABLE public.menu_item ADD COLUMN IF NOT EXISTS ai_typical_price numeric(12, 2);

UPDATE public.alembic_version SET version_num = '0008_menu_item_ai_typical_price' WHERE version_num = '0007_place_phone';

-- 확인
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'menu_item' AND column_name = 'ai_typical_price';
