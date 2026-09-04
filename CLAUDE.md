# 운영 관례

## Supabase 마이그레이션은 Claude가 직접 실행한다 (2026-09-04 확정)

Render 무료 플랜엔 Alembic 자동 실행이 없어서, `scripts/supabase_migration_XXXX.sql`
파일들은 Supabase SQL Editor에서 수동 실행이 필요하다. **이걸 사용자에게 붙여넣고
실행하라고 안내하지 않는다** — Supabase MCP(`mcp__Supabase__execute_sql`,
project_id `mmllgsgibppwsirwryzt`)로 Claude가 직접 적용하고, 적용 후 스키마를
SELECT로 재확인한 뒤 사용자에게는 결과만 보고한다.

이유: 사용자가 SQL Editor에 붙여넣다가 오류를 겪은 적이 있다(0027).
`ALTER TYPE ... ADD VALUE`가 같은 트랜잭션 안의 다른 문장과 같이 실행되면
막히는 PostgreSQL 제약(0025에서 실제로 겪음) 때문에 여러 블록으로 나눠 각각
따로 실행해야 하는 마이그레이션도 있어서, 사람이 직접 하면 실수하기 쉽다.

`scripts/supabase_migration_XXXX.sql` 파일 자체는 계속 만든다(수동 실행이
필요한 경우를 대비한 기록/백업 경로로 남겨두되, 정상 흐름에서는 Claude가
먼저 직접 적용한다).
