-- SaveMap: 절약액 계산 출처(offer.benchmark_source: region/ai) 컬럼 추가
-- Supabase SQL Editor에서 그대로 실행하세요. (재실행해도 안전)

ALTER TABLE public.offer ADD COLUMN IF NOT EXISTS benchmark_source varchar(16);

UPDATE public.alembic_version SET version_num = '0012_offer_benchmark_source' WHERE version_num = '0011_menu_report_xp';

-- 확인
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'offer' AND column_name = 'benchmark_source';
