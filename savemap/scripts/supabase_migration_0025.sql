-- 0025_place_visit_and_growth: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요.
-- 방문 GPS 인증(공식 기준, 2026-09-01) + 성장 이벤트 기록 + 좌표 출처 + 신규 xp_reason 2종.

ALTER TYPE public.xp_reason ADD VALUE IF NOT EXISTS 'PLACE_VISIT';
ALTER TYPE public.xp_reason ADD VALUE IF NOT EXISTS 'PLACE_RECOMMEND';

ALTER TABLE public.xp_ledger
    ADD COLUMN IF NOT EXISTS place_id integer REFERENCES public.place(id) ON DELETE SET NULL;

ALTER TABLE public.place
    ADD COLUMN IF NOT EXISTS location_source varchar(32);

CREATE TABLE IF NOT EXISTS public.place_visit (
    id serial PRIMARY KEY,
    user_id varchar(64) NOT NULL,
    place_id integer NOT NULL REFERENCES public.place(id) ON DELETE CASCADE,
    lat numeric(9,6) NOT NULL,
    lng numeric(9,6) NOT NULL,
    gps_accuracy numeric(6,2) NOT NULL,
    distance_at_visit numeric(8,2) NOT NULL,
    visit_date date NOT NULL,
    client_timestamp timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_place_visit_user_place_date
    ON public.place_visit (user_id, place_id, visit_date);

CREATE INDEX IF NOT EXISTS ix_place_visit_user_id
    ON public.place_visit (user_id);

UPDATE public.alembic_version SET version_num = '0025_place_visit_and_growth' WHERE version_num = '0024_user_digest';

-- 확인
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'place_visit';

SELECT column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'xp_ledger' AND column_name = 'place_id';

SELECT enumlabel FROM pg_enum
WHERE enumtypid = 'public.xp_reason'::regtype
ORDER BY enumsortorder;
