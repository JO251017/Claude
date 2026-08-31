-- 0022_price_discovery: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요.
--
-- 주의: enum 라벨은 SourceType.name(대문자)이다 — .value(소문자)가 아니다.
-- 이 프로젝트의 SAEnum(PyEnum) 컬럼은 전부 .name을 DB 라벨로 저장한다(예:
-- xp_reason에 이미 'STORE_VISIT_UPDATE'로 들어가 있는 것과 동일 관례).

ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'S6_AI_DISCOVERY_OFFICIAL';
ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'S6_AI_DISCOVERY_WEB';

DO $$ BEGIN
    CREATE TYPE discovery_job_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'MANUAL_REVIEW');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS public.price_discovery_job (
    id SERIAL PRIMARY KEY,
    place_id INTEGER NOT NULL REFERENCES public.place(id) ON DELETE CASCADE,
    status discovery_job_status NOT NULL DEFAULT 'PENDING',
    priority INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempted_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_code VARCHAR(32),
    result_summary VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_price_discovery_job_place_id ON public.price_discovery_job (place_id);
CREATE INDEX IF NOT EXISTS ix_price_discovery_job_status_priority ON public.price_discovery_job (status, priority);

-- 동일 매장에 pending/processing 작업이 동시에 여럿 안 생기게 DB에서 막는다
-- (부분 유니크 인덱스 — completed/failed/manual_review는 여러 건 허용).
CREATE UNIQUE INDEX IF NOT EXISTS ux_price_discovery_job_active_place
    ON public.price_discovery_job (place_id)
    WHERE status IN ('PENDING', 'PROCESSING');

UPDATE public.alembic_version SET version_num = '0022_price_discovery' WHERE version_num = '0021_price_history';

-- 확인
SELECT enumlabel FROM pg_enum WHERE enumtypid = 'source_type'::regtype ORDER BY enumsortorder;
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'price_discovery_job';
