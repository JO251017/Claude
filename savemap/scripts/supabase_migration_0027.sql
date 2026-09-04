-- 0027_offer_benchmark_radius: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요.
-- 실측 비교 반경(3km → 부족하면 10km)을 오퍼에 굳혀 저장한다 — 화면 문구를
-- "주변"과 "같은 지역"으로 정직하게 가르기 위한 값.
--
-- 이 파일은 ALTER TYPE이 없어 통째로 한 번에 실행해도 안전합니다.

ALTER TABLE public.offer
    ADD COLUMN IF NOT EXISTS benchmark_radius_km numeric(5,2);

UPDATE public.alembic_version SET version_num = '0027_offer_benchmark_radius'
WHERE version_num = '0026_pet_stage_message';

-- 확인
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'offer' AND column_name = 'benchmark_radius_km';
