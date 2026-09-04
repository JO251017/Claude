--
-- PostgreSQL database dump
--


-- Dumped from database version 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: postgis; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;


--
-- Name: EXTENSION postgis; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION postgis IS 'PostGIS geometry and geography spatial types and functions';


--
-- Name: category_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.category_type AS ENUM (
    'FREE',
    'DISCOUNT',
    'CLOSING_SOON',
    'FREE_PARKING',
    'LOCAL_BENEFIT'
);


--
-- Name: layer_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.layer_type AS ENUM (
    'CORE_BASE',
    'REGULAR',
    'FLASH'
);


--
-- Name: payment_method_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.payment_method_type AS ENUM (
    'CARD',
    'TELCO',
    'LOCAL_CURRENCY'
);


--
-- Name: report_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.report_status AS ENUM (
    'PENDING',
    'VERIFIED',
    'REJECTED',
    'EXPIRED'
);


--
-- Name: source_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.source_type AS ENUM (
    'S1_PUBLIC',
    'S2_PARTNER',
    'S3_MERCHANT',
    'S4_REPORT',
    'S5_VERIFICATION'
);


--
-- Name: verdict_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.verdict_type AS ENUM (
    'AVAILABLE',
    'SOLD_OUT'
);


--
-- Name: xp_reason; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.xp_reason AS ENUM (
    'VALID_REPORT',
    'FIELD_VERIFICATION'
);


SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: offer; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.offer (
    id integer NOT NULL,
    place_id integer NOT NULL,
    source public.source_type NOT NULL,
    layer public.layer_type NOT NULL,
    category public.category_type NOT NULL,
    title character varying(255) NOT NULL,
    base_price numeric(12,2),
    store_discount numeric(12,2),
    valid_from timestamp with time zone,
    expires_at timestamp with time zone,
    ttl_sec integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: offer_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.offer_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: offer_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.offer_id_seq OWNED BY public.offer.id;


--
-- Name: offer_payment_benefit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.offer_payment_benefit (
    id integer NOT NULL,
    offer_id integer NOT NULL,
    method_type public.payment_method_type NOT NULL,
    benefit_rate numeric(5,4),
    benefit_amount numeric(12,2)
);


--
-- Name: offer_payment_benefit_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.offer_payment_benefit_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: offer_payment_benefit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.offer_payment_benefit_id_seq OWNED BY public.offer_payment_benefit.id;


--
-- Name: payment_method_derived; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payment_method_derived (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    method_type public.payment_method_type NOT NULL,
    owned boolean NOT NULL,
    grade character varying(32),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: payment_method_derived_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.payment_method_derived_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: payment_method_derived_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.payment_method_derived_id_seq OWNED BY public.payment_method_derived.id;


--
-- Name: place; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.place (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    address character varying(500),
    kakao_place_id character varying(64),
    geom public.geometry(Point,4326) NOT NULL,
    h3_r9 bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: place_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.place_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: place_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.place_id_seq OWNED BY public.place.id;


--
-- Name: trust_score; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trust_score (
    id integer NOT NULL,
    subject_type character varying(32) NOT NULL,
    subject_id integer NOT NULL,
    score numeric(5,4) NOT NULL,
    recomputed_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: trust_score_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.trust_score_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trust_score_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.trust_score_id_seq OWNED BY public.trust_score.id;


--
-- Name: user_report; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_report (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    image_url character varying(1024) NOT NULL,
    ocr_json jsonb,
    ai_category public.category_type,
    status public.report_status NOT NULL,
    geom public.geometry(Point,4326),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_report_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_report_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_report_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_report_id_seq OWNED BY public.user_report.id;


--
-- Name: verification; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.verification (
    id integer NOT NULL,
    report_id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    verdict public.verdict_type NOT NULL,
    weight numeric(5,4) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: verification_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.verification_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: verification_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.verification_id_seq OWNED BY public.verification.id;


--
-- Name: xp_ledger; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.xp_ledger (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    delta integer NOT NULL,
    reason public.xp_reason NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: xp_ledger_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.xp_ledger_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: xp_ledger_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.xp_ledger_id_seq OWNED BY public.xp_ledger.id;


--
-- Name: offer id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offer ALTER COLUMN id SET DEFAULT nextval('public.offer_id_seq'::regclass);


--
-- Name: offer_payment_benefit id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offer_payment_benefit ALTER COLUMN id SET DEFAULT nextval('public.offer_payment_benefit_id_seq'::regclass);


--
-- Name: payment_method_derived id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_method_derived ALTER COLUMN id SET DEFAULT nextval('public.payment_method_derived_id_seq'::regclass);


--
-- Name: place id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.place ALTER COLUMN id SET DEFAULT nextval('public.place_id_seq'::regclass);


--
-- Name: trust_score id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trust_score ALTER COLUMN id SET DEFAULT nextval('public.trust_score_id_seq'::regclass);


--
-- Name: user_report id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_report ALTER COLUMN id SET DEFAULT nextval('public.user_report_id_seq'::regclass);


--
-- Name: verification id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification ALTER COLUMN id SET DEFAULT nextval('public.verification_id_seq'::regclass);


--
-- Name: xp_ledger id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.xp_ledger ALTER COLUMN id SET DEFAULT nextval('public.xp_ledger_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: offer_payment_benefit offer_payment_benefit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offer_payment_benefit
    ADD CONSTRAINT offer_payment_benefit_pkey PRIMARY KEY (id);


--
-- Name: offer offer_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offer
    ADD CONSTRAINT offer_pkey PRIMARY KEY (id);


--
-- Name: payment_method_derived payment_method_derived_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_method_derived
    ADD CONSTRAINT payment_method_derived_pkey PRIMARY KEY (id);


--
-- Name: place place_kakao_place_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.place
    ADD CONSTRAINT place_kakao_place_id_key UNIQUE (kakao_place_id);


--
-- Name: place place_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.place
    ADD CONSTRAINT place_pkey PRIMARY KEY (id);


--
-- Name: trust_score trust_score_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trust_score
    ADD CONSTRAINT trust_score_pkey PRIMARY KEY (id);


--
-- Name: trust_score uq_trust_subject; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trust_score
    ADD CONSTRAINT uq_trust_subject UNIQUE (subject_type, subject_id);


--
-- Name: user_report user_report_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_report
    ADD CONSTRAINT user_report_pkey PRIMARY KEY (id);


--
-- Name: verification verification_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification
    ADD CONSTRAINT verification_pkey PRIMARY KEY (id);


--
-- Name: xp_ledger xp_ledger_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.xp_ledger
    ADD CONSTRAINT xp_ledger_pkey PRIMARY KEY (id);


--
-- Name: ix_offer_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_offer_category ON public.offer USING btree (category);


--
-- Name: ix_offer_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_offer_expires_at ON public.offer USING btree (expires_at);


--
-- Name: ix_offer_layer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_offer_layer ON public.offer USING btree (layer);


--
-- Name: ix_offer_place_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_offer_place_id ON public.offer USING btree (place_id);


--
-- Name: ix_payment_method_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_payment_method_user_id ON public.payment_method_derived USING btree (user_id);


--
-- Name: ix_place_geom_gist; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_place_geom_gist ON public.place USING gist (geom);


--
-- Name: ix_place_h3_r9; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_place_h3_r9 ON public.place USING btree (h3_r9);


--
-- Name: ix_user_report_geom_gist; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_report_geom_gist ON public.user_report USING gist (geom);


--
-- Name: ix_verification_report_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_verification_report_id ON public.verification USING btree (report_id);


--
-- Name: ix_xp_ledger_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_xp_ledger_user_id ON public.xp_ledger USING btree (user_id);


--
-- Name: offer_payment_benefit offer_payment_benefit_offer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offer_payment_benefit
    ADD CONSTRAINT offer_payment_benefit_offer_id_fkey FOREIGN KEY (offer_id) REFERENCES public.offer(id) ON DELETE CASCADE;


--
-- Name: offer offer_place_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offer
    ADD CONSTRAINT offer_place_id_fkey FOREIGN KEY (place_id) REFERENCES public.place(id) ON DELETE CASCADE;


--
-- Name: verification verification_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification
    ADD CONSTRAINT verification_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.user_report(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--



INSERT INTO public.alembic_version (version_num) VALUES ('0001_initial');
