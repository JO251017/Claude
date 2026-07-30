-- SaveMap: 메뉴 가격 등록만으로도 지도 검색에 뜨도록 오퍼 자동 연결
-- Supabase SQL Editor에서 그대로 실행하세요.

ALTER TABLE public.offer ADD COLUMN menu_item_id integer;
ALTER TABLE ONLY public.offer
    ADD CONSTRAINT offer_menu_item_id_fkey FOREIGN KEY (menu_item_id) REFERENCES public.menu_item(id) ON DELETE CASCADE;
CREATE INDEX ix_offer_menu_item_id ON public.offer USING btree (menu_item_id);

UPDATE public.alembic_version SET version_num = '0006_offer_menu_item_link' WHERE version_num = '0005_menu_price_visit';

-- 확인
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'offer' AND column_name = 'menu_item_id';
