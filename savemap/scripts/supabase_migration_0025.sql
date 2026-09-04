-- 0025_place_visit_and_growth: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요.
-- 방문 GPS 인증(공식 기준, 2026-09-01) + 성장 이벤트 기록 + 좌표 출처 + 신규 xp_reason 2종.
--
-- *** 주의: 이 파일을 통째로 한 번에 실행하지 마세요 ***
-- PostgreSQL은 ALTER TYPE ... ADD VALUE를 같은 트랜잭션 안에서 다른 문장과
-- 함께 실행하는 걸 허용하지 않습니다. Supabase SQL Editor는 붙여넣은 내용을
-- 하나의 트랜잭션으로 실행하므로, STEP 1을 다른 문장과 같이 붙여넣으면
-- "ALTER TYPE ... ADD VALUE cannot run inside a transaction block" 에러가
-- 나면서 전체가 롤백됩니다(2026-09-01 실사용 중 확인). 아래 STEP 1 → STEP 2
-- 순서로, 반드시 각각 따로 붙여넣고 각각 Run을 눌러주세요.

-- ============================================================
-- STEP 1 — 이 블록만 붙여넣고 Run (완료 후 STEP 2로)
-- ============================================================
ALTER TYPE public.xp_reason ADD VALUE IF NOT EXISTS 'PLACE_VISIT';

-- ============================================================
-- STEP 1-2 — 이 블록만 붙여넣고 Run (완료 후 STEP 2로)
-- ============================================================
ALTER TYPE public.xp_reason ADD VALUE IF NOT EXISTS 'PLACE_RECOMMEND';

-- ============================================================
-- STEP 2 — STEP 1, 1-2가 각각 성공한 뒤, 이 블록을 붙여넣고 Run
-- (일반 DDL이라 한 번에 같이 실행해도 안전합니다)
-- ============================================================
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

-- ============================================================
-- 확인 (STEP 2까지 끝난 뒤 실행)
-- ============================================================
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'place_visit';

SELECT column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'xp_ledger' AND column_name = 'place_id';

SELECT enumlabel FROM pg_enum
WHERE enumtypid = 'public.xp_reason'::regtype
ORDER BY enumsortorder;
