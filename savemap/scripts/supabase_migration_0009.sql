-- SaveMap: 매장별 "식사 인증 횟수" 집계용 savings_certification.place_id 컬럼 추가
-- Supabase SQL Editor에서 그대로 실행하세요. (재실행해도 안전)

ALTER TABLE public.savings_certification ADD COLUMN IF NOT EXISTS place_id integer REFERENCES public.place(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_savings_certification_place_id ON public.savings_certification (place_id);

UPDATE public.alembic_version SET version_num = '0009_savings_certification_place_id' WHERE version_num = '0008_menu_item_ai_typical_price';

-- 확인
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'savings_certification' AND column_name = 'place_id';
