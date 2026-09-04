-- 0021_price_history: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요.

CREATE TABLE IF NOT EXISTS public.price_history (
    id SERIAL PRIMARY KEY,
    menu_item_id INTEGER NOT NULL REFERENCES public.menu_item(id) ON DELETE CASCADE,
    place_id INTEGER NOT NULL REFERENCES public.place(id) ON DELETE CASCADE,
    price NUMERIC(12, 2) NOT NULL,
    source_type source_type NOT NULL,
    source_url VARCHAR(1024),
    observed_at TIMESTAMPTZ NOT NULL,
    evidence_text VARCHAR(500),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_price_history_menu_item_id ON public.price_history (menu_item_id);
CREATE INDEX IF NOT EXISTS ix_price_history_menu_item_current ON public.price_history (menu_item_id, is_current);

UPDATE public.alembic_version SET version_num = '0021_price_history' WHERE version_num = '0020_place_local_currency';

-- 확인
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'price_history';
