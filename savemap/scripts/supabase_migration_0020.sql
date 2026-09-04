-- 0020_place_local_currency: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요.

ALTER TABLE public.place
    ADD COLUMN IF NOT EXISTS accepts_local_currency boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS local_currency_verified_at timestamptz;

UPDATE public.alembic_version SET version_num = '0020_place_local_currency' WHERE version_num = '0019_offer_benchmark_metadata';

-- 확인
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'place'
  AND column_name IN ('accepts_local_currency', 'local_currency_verified_at');
