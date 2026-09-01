-- 0026_pet_stage_message: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요.
-- AI MVP §D — 펫 레벨업 축하 대사 전역 캐시(사용자별 아님, 단계별 하나).
--
-- 이 파일 자체는 ALTER TYPE이 없어 통째로 한 번에 실행해도 안전합니다.
-- 단, 0025_place_visit_and_growth.sql을 먼저(그 파일 안내대로 STEP별로
-- 나눠서) 성공시킨 뒤에 실행하세요 — 0025가 먼저 실패한 채로 같은 편집창에
-- 이어붙여 실행하면 그 트랜잭션이 이미 중단된 상태라 이 파일도 같이
-- 에러(current transaction is aborted)로 실패합니다(2026-09-01 실사용 중 확인).

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
