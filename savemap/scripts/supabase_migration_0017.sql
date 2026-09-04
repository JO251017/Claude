-- SaveMap: regional_price_stat 테이블 추가 (한국소비자원 참가격 외식비 시도별 평균가)
-- Supabase SQL Editor에서 그대로 실행하세요. (재실행해도 안전)

CREATE TABLE IF NOT EXISTS public.regional_price_stat (
    id serial PRIMARY KEY,
    dish varchar(64) NOT NULL,
    region varchar(32) NOT NULL,
    price numeric(12, 2) NOT NULL,
    survey_period varchar(16),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_regional_price_dish_region UNIQUE (dish, region)
);

CREATE INDEX IF NOT EXISTS ix_regional_price_dish_region ON public.regional_price_stat (dish, region);

UPDATE public.alembic_version SET version_num = '0017_regional_price_stat' WHERE version_num = '0016_menu_item_normalized_name';

-- 확인
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'regional_price_stat';
