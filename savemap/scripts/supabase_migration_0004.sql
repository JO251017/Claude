-- SaveMap: MAP 카드(오퍼) 단위 "아직 있어요/없어졌어요" 신뢰도 검증 테이블 추가
-- + XP 사유에 절약 인증(SAVINGS_CERTIFIED) 추가
-- Supabase SQL Editor에 그대로 붙여넣고 실행하세요.

ALTER TYPE public.xp_reason ADD VALUE IF NOT EXISTS 'SAVINGS_CERTIFIED';

CREATE TABLE public.offer_verification (
    id integer NOT NULL,
    offer_id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    verdict public.verdict_type NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE SEQUENCE public.offer_verification_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.offer_verification_id_seq OWNED BY public.offer_verification.id;
ALTER TABLE ONLY public.offer_verification
    ALTER COLUMN id SET DEFAULT nextval('public.offer_verification_id_seq'::regclass);
ALTER TABLE ONLY public.offer_verification
    ADD CONSTRAINT offer_verification_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.offer_verification
    ADD CONSTRAINT offer_verification_offer_id_fkey FOREIGN KEY (offer_id) REFERENCES public.offer(id) ON DELETE CASCADE;
CREATE INDEX ix_offer_verification_offer_id ON public.offer_verification USING btree (offer_id);

UPDATE public.alembic_version SET version_num = '0004_offer_verification' WHERE version_num = '0003_savings_certification_asset';

-- 확인
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'offer_verification';
