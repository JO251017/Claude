-- 0028_menu_synonym_candidate: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요(단, 이 세션에서는 Claude가 직접
-- Supabase MCP로 적용한다 — CLAUDE.md 운영 관례 참고. 이 파일은 백업 기록용).
--
-- AI가 찾은 "표기만 다른 것 같은 메뉴명 쌍" 후보를 저장한다. 사람이 검토하기
-- 전까지는 실제 정규화 규칙(app/engine/menu_name.py의 _SYNONYMS)에 반영되지
-- 않는다 — 잘못 합치면 값이 다른 메뉴끼리 비교해 없는 절약률을 만들어낸다.
--
-- ALTER TYPE이 없어 통째로 한 번에 실행해도 안전합니다.

CREATE TABLE IF NOT EXISTS public.menu_synonym_candidate (
    id serial PRIMARY KEY,
    variant varchar(64) NOT NULL,
    canonical varchar(64) NOT NULL,
    reason varchar(200),
    variant_places integer,
    canonical_places integer,
    status varchar(16) NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_menu_synonym_candidate_pair UNIQUE (variant, canonical)
);

CREATE INDEX IF NOT EXISTS ix_menu_synonym_candidate_status
    ON public.menu_synonym_candidate (status);

UPDATE public.alembic_version SET version_num = '0028_menu_synonym_candidate'
WHERE version_num = '0027_offer_benchmark_radius';

-- 확인
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'menu_synonym_candidate';
