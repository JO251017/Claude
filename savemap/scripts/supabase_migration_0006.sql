-- SaveMap: 메뉴 가격 등록만으로도 지도 검색에 뜨도록 오퍼 자동 연결
-- Supabase SQL Editor에서 그대로 실행하세요.
-- (재실행해도 안전하도록 각 단계마다 이미 적용됐는지 확인 후 건너뜁니다)

ALTER TABLE public.offer ADD COLUMN IF NOT EXISTS menu_item_id integer;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'offer_menu_item_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.offer
            ADD CONSTRAINT offer_menu_item_id_fkey FOREIGN KEY (menu_item_id)
            REFERENCES public.menu_item(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_offer_menu_item_id ON public.offer USING btree (menu_item_id);

UPDATE public.alembic_version SET version_num = '0006_offer_menu_item_link' WHERE version_num = '0005_menu_price_visit';

-- 확인 (컬럼 1개, 제약조건 1개, 인덱스 1개가 나와야 정상)
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'offer' AND column_name = 'menu_item_id';

SELECT conname FROM pg_constraint WHERE conname = 'offer_menu_item_id_fkey';

SELECT indexname FROM pg_indexes WHERE indexname = 'ix_offer_menu_item_id';
