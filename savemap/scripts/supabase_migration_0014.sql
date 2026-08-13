-- SaveMap: EXCHANGE 재도입 — savings_asset.offer_id/place_id/place_name 추가
-- Supabase SQL Editor에서 그대로 실행하세요. (재실행해도 안전)

ALTER TABLE public.savings_asset
    ADD COLUMN IF NOT EXISTS offer_id integer REFERENCES public.offer(id) ON DELETE SET NULL;

ALTER TABLE public.savings_asset
    ADD COLUMN IF NOT EXISTS place_id integer REFERENCES public.place(id) ON DELETE SET NULL;

ALTER TABLE public.savings_asset
    ADD COLUMN IF NOT EXISTS place_name character varying(255);

CREATE INDEX IF NOT EXISTS ix_savings_asset_place_id ON public.savings_asset (place_id);

UPDATE public.alembic_version SET version_num = '0014_savings_asset_offer_place' WHERE version_num = '0013_merchant_verification';

-- 확인
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'savings_asset'
AND column_name IN ('offer_id', 'place_id', 'place_name');
