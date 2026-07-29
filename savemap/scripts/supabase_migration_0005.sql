-- SaveMap: 음식점/카페 메뉴 가격 비교 + GPS 50m 방문 인증 + 관심도
-- Supabase SQL Editor에 그대로 붙여넣고 실행하세요.

ALTER TYPE public.xp_reason ADD VALUE IF NOT EXISTS 'STORE_VISIT_UPDATE';
ALTER TYPE public.xp_reason ADD VALUE IF NOT EXISTS 'RECEIPT_VERIFIED';

CREATE TYPE public.business_status AS ENUM ('OPEN', 'CLOSED', 'TEMP_CLOSED', 'UNKNOWN');

CREATE TABLE public.menu_item (
    id integer NOT NULL,
    place_id integer NOT NULL,
    name character varying(255) NOT NULL,
    price numeric(12,2) NOT NULL,
    source public.source_type NOT NULL,
    source_url character varying(1024),
    verified_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE public.menu_item_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.menu_item_id_seq OWNED BY public.menu_item.id;
ALTER TABLE ONLY public.menu_item
    ALTER COLUMN id SET DEFAULT nextval('public.menu_item_id_seq'::regclass);
ALTER TABLE ONLY public.menu_item
    ADD CONSTRAINT menu_item_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.menu_item
    ADD CONSTRAINT menu_item_place_id_fkey FOREIGN KEY (place_id) REFERENCES public.place(id) ON DELETE CASCADE;
CREATE INDEX ix_menu_item_place_id ON public.menu_item USING btree (place_id);
CREATE INDEX ix_menu_item_name ON public.menu_item USING btree (name);

CREATE TABLE public.store_status_update (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    place_id integer NOT NULL,
    status public.business_status NOT NULL,
    lat numeric(9,6) NOT NULL,
    lng numeric(9,6) NOT NULL,
    distance_m numeric(8,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE public.store_status_update_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.store_status_update_id_seq OWNED BY public.store_status_update.id;
ALTER TABLE ONLY public.store_status_update
    ALTER COLUMN id SET DEFAULT nextval('public.store_status_update_id_seq'::regclass);
ALTER TABLE ONLY public.store_status_update
    ADD CONSTRAINT store_status_update_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.store_status_update
    ADD CONSTRAINT store_status_update_place_id_fkey FOREIGN KEY (place_id) REFERENCES public.place(id) ON DELETE CASCADE;
CREATE INDEX ix_store_status_update_place_id ON public.store_status_update USING btree (place_id);

CREATE TABLE public.store_interest (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    place_id integer NOT NULL,
    first_interested_at timestamp with time zone DEFAULT now() NOT NULL,
    last_interested_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE public.store_interest_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.store_interest_id_seq OWNED BY public.store_interest.id;
ALTER TABLE ONLY public.store_interest
    ALTER COLUMN id SET DEFAULT nextval('public.store_interest_id_seq'::regclass);
ALTER TABLE ONLY public.store_interest
    ADD CONSTRAINT store_interest_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.store_interest
    ADD CONSTRAINT store_interest_place_id_fkey FOREIGN KEY (place_id) REFERENCES public.place(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.store_interest
    ADD CONSTRAINT uq_store_interest_user_place UNIQUE (user_id, place_id);
CREATE INDEX ix_store_interest_place_id ON public.store_interest USING btree (place_id);

UPDATE public.alembic_version SET version_num = '0005_menu_price_visit' WHERE version_num = '0004_offer_verification';

-- 확인
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name IN ('menu_item', 'store_status_update', 'store_interest');
