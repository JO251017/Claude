-- SaveMap: 제보 → 실제 Place/Offer 게시 연결 — user_report.place_id/offer_id 추가
-- Supabase SQL Editor에서 그대로 실행하세요. (재실행해도 안전)

ALTER TABLE public.user_report
    ADD COLUMN IF NOT EXISTS place_id integer REFERENCES public.place(id) ON DELETE SET NULL;

ALTER TABLE public.user_report
    ADD COLUMN IF NOT EXISTS offer_id integer REFERENCES public.offer(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_user_report_place_id ON public.user_report (place_id);

UPDATE public.alembic_version SET version_num = '0015_user_report_place_offer' WHERE version_num = '0014_savings_asset_offer_place';

-- 확인
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'user_report'
AND column_name IN ('place_id', 'offer_id');
