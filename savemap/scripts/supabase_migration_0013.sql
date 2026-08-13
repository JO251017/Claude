-- SaveMap: 사업자 콘솔 접근 제어 최소 기능 — merchant_verification 테이블 추가
-- Supabase SQL Editor에서 그대로 실행하세요. (재실행해도 안전)

CREATE TABLE IF NOT EXISTS public.merchant_verification (
    id serial PRIMARY KEY,
    user_id character varying(64) NOT NULL,
    note character varying(255),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_merchant_verification_user UNIQUE (user_id)
);

UPDATE public.alembic_version SET version_num = '0013_merchant_verification' WHERE version_num = '0012_offer_benchmark_source';

-- 확인
SELECT 'merchant_verification' AS item FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'merchant_verification';
