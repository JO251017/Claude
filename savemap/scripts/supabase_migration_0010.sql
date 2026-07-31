-- SaveMap: AI 절약 리포트용 스키마 추가
--   1) place.category_name — 카카오가 준 실제 업종 문자열 (메뉴 대신 업종을 보여줌)
--   2) place_recommendation — 사용자 추천(👍), 리포트 "판단 근거"의 실제 집계 원천
-- Supabase SQL Editor에서 그대로 실행하세요. (재실행해도 안전)

ALTER TABLE public.place ADD COLUMN IF NOT EXISTS category_name character varying(255);

CREATE TABLE IF NOT EXISTS public.place_recommendation (
    id serial PRIMARY KEY,
    user_id character varying(64) NOT NULL,
    place_id integer NOT NULL REFERENCES public.place(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_place_recommendation_user_place UNIQUE (user_id, place_id)
);
CREATE INDEX IF NOT EXISTS ix_place_recommendation_place_id ON public.place_recommendation (place_id);

UPDATE public.alembic_version SET version_num = '0010_place_recommendation' WHERE version_num = '0009_savings_cert_place_id';

-- 확인 (2행이 나와야 정상: place.category_name 컬럼 + place_recommendation 테이블)
SELECT 'place.category_name' AS item FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'place' AND column_name = 'category_name'
UNION ALL
SELECT 'place_recommendation' FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'place_recommendation';
