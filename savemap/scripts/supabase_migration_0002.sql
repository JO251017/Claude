ALTER TABLE public.place ADD COLUMN owner_user_id character varying(64);
CREATE INDEX ix_place_owner_user_id ON public.place USING btree (owner_user_id);
UPDATE public.alembic_version SET version_num = '0002_place_owner' WHERE version_num = '0001_initial';
