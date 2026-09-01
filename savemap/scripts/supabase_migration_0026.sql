-- 0026_pet_stage_message: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요.
-- AI MVP §D — 펫 레벨업 축하 대사 전역 캐시(사용자별 아님, 단계별 하나).

CREATE TABLE IF NOT EXISTS public.pet_stage_message (
    id serial PRIMARY KEY,
    stage_index integer NOT NULL,
    message varchar(200) NOT NULL,
    source varchar(16) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_pet_stage_message_stage_index
    ON public.pet_stage_message (stage_index);

UPDATE public.alembic_version SET version_num = '0026_pet_stage_message' WHERE version_num = '0025_place_visit_and_growth';

-- 확인
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'pet_stage_message';
