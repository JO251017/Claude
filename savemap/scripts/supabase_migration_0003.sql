-- SaveMap 리디자인: 실제 절약 인증 + 절약 자산 교환(EXCHANGE) 테이블 추가
-- Supabase SQL Editor에 그대로 붙여넣고 실행하세요.

CREATE TYPE public.certification_method AS ENUM ('SIMPLE', 'RECEIPT');
CREATE TYPE public.certification_confidence AS ENUM ('HIGH', 'MEDIUM', 'LOW');
CREATE TYPE public.asset_status AS ENUM ('AVAILABLE', 'EXCHANGED');

CREATE TABLE public.savings_certification (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    offer_id integer,
    place_name character varying(255) NOT NULL,
    base_price numeric(12,2) NOT NULL,
    actual_price numeric(12,2) NOT NULL,
    amount numeric(12,2) NOT NULL,
    method public.certification_method NOT NULL,
    confidence public.certification_confidence NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE SEQUENCE public.savings_certification_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.savings_certification_id_seq OWNED BY public.savings_certification.id;
ALTER TABLE ONLY public.savings_certification
    ALTER COLUMN id SET DEFAULT nextval('public.savings_certification_id_seq'::regclass);
ALTER TABLE ONLY public.savings_certification
    ADD CONSTRAINT savings_certification_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.savings_certification
    ADD CONSTRAINT savings_certification_offer_id_fkey FOREIGN KEY (offer_id) REFERENCES public.offer(id) ON DELETE SET NULL;
CREATE INDEX ix_savings_certification_user_id ON public.savings_certification USING btree (user_id);

CREATE TABLE public.savings_asset (
    id integer NOT NULL,
    owner_user_id character varying(64) NOT NULL,
    category character varying(32) NOT NULL,
    title character varying(255) NOT NULL,
    condition_text character varying(500),
    estimated_value numeric(12,2),
    expires_at timestamp with time zone,
    status public.asset_status DEFAULT 'AVAILABLE'::public.asset_status NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE SEQUENCE public.savings_asset_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.savings_asset_id_seq OWNED BY public.savings_asset.id;
ALTER TABLE ONLY public.savings_asset
    ALTER COLUMN id SET DEFAULT nextval('public.savings_asset_id_seq'::regclass);
ALTER TABLE ONLY public.savings_asset
    ADD CONSTRAINT savings_asset_pkey PRIMARY KEY (id);
CREATE INDEX ix_savings_asset_owner_user_id ON public.savings_asset USING btree (owner_user_id);

UPDATE public.alembic_version SET version_num = '0003_savings_certification_asset' WHERE version_num = '0002_place_owner';

-- 확인
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name IN ('savings_certification', 'savings_asset');
