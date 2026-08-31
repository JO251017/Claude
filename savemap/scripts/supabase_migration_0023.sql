-- 0023_offer_ai_one_line: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요.

ALTER TABLE public.offer
    ADD COLUMN IF NOT EXISTS ai_one_line varchar(200),
    ADD COLUMN IF NOT EXISTS ai_one_line_generated_at timestamptz;

UPDATE public.alembic_version SET version_num = '0023_offer_ai_one_line' WHERE version_num = '0022_price_discovery';

-- 확인
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'offer'
  AND column_name IN ('ai_one_line', 'ai_one_line_generated_at');
