-- 0029_franchise_sugg_keywords: Render는 Alembic을 자동 실행하지 않으므로
-- Supabase SQL Editor에서 수동 실행 필요(단, 이 세션에서는 Claude가 직접
-- Supabase MCP로 적용한다 — CLAUDE.md 운영 관례 참고. 이 파일은 백업 기록용).
--
-- AI가 찾은 "브랜드 상호명 매칭 키워드" 제안을 저장한다. match_keywords와는
-- 완전히 별개 컬럼이라, 여기에 뭐가 들어와도 실제 상호명 매칭(franchise_price.
-- matches_brand)에는 전혀 쓰이지 않는다. 브랜드 매칭이 잘못되면 엉뚱한 매장에
-- 엉뚱한 가격이 붙는다 — 사람이 검토해 직접 match_keywords로 옮겨야만 적용된다.
--
-- ALTER TYPE이 없어 통째로 한 번에 실행해도 안전합니다.

ALTER TABLE public.franchise_brand
    ADD COLUMN IF NOT EXISTS suggested_match_keywords varchar(512);

UPDATE public.alembic_version SET version_num = '0029_franchise_sugg_keywords'
WHERE version_num = '0028_menu_synonym_candidate';

-- 확인
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'franchise_brand'
ORDER BY ordinal_position;
