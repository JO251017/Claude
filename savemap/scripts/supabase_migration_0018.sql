-- SaveMap: franchise_brand / franchise_price 테이블 추가 (프랜차이즈 본사 공식
-- 가격표를 상호명 매칭으로 매장에 적용하기 위한 저장소)
-- Supabase SQL Editor에서 그대로 실행하세요. (재실행해도 안전)

CREATE TABLE IF NOT EXISTS public.franchise_brand (
    id serial PRIMARY KEY,
    name varchar(128) NOT NULL UNIQUE,
    match_keywords varchar(512),
    official_url varchar(1024),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.franchise_price (
    id serial PRIMARY KEY,
    brand_id integer NOT NULL REFERENCES public.franchise_brand(id) ON DELETE CASCADE,
    item_name varchar(255) NOT NULL,
    normalized_item_name varchar(255) NOT NULL DEFAULT '',
    price numeric(12, 2) NOT NULL,
    effective_period varchar(16),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_franchise_price_item UNIQUE (brand_id, normalized_item_name)
);

CREATE INDEX IF NOT EXISTS ix_franchise_price_brand_id ON public.franchise_price (brand_id);

UPDATE public.alembic_version SET version_num = '0018_franchise_price' WHERE version_num = '0017_regional_price_stat';

-- 확인
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name IN ('franchise_brand', 'franchise_price');
