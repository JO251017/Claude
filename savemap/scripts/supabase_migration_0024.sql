-- 0024_user_digest: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요.

CREATE TABLE IF NOT EXISTS public.user_digest (
    id serial PRIMARY KEY,
    user_id varchar(64) NOT NULL,
    week_start timestamptz NOT NULL,
    summary_text varchar(300) NOT NULL,
    source varchar(16) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_user_digest_user_week
    ON public.user_digest (user_id, week_start);

UPDATE public.alembic_version SET version_num = '0024_user_digest' WHERE version_num = '0023_offer_ai_one_line';

-- 확인
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'user_digest';
