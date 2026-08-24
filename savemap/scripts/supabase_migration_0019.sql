-- 0019_offer_benchmark_metadata: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요.

CREATE INDEX IF NOT EXISTS ix_offer_menu_item_id ON public.offer (menu_item_id);

ALTER TABLE public.offer
    ADD COLUMN IF NOT EXISTS benchmark_sample_count integer,
    ADD COLUMN IF NOT EXISTS benchmark_synced_at timestamptz;

UPDATE public.alembic_version SET version_num = '0019_offer_benchmark_metadata' WHERE version_num = '0018_franchise_price';

-- 확인
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'offer'
  AND column_name IN ('benchmark_sample_count', 'benchmark_synced_at');
