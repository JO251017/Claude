-- SaveMap: 제보 사진 업로드용 Storage 버킷 생성 (사진 한 장 제보 UX에 필요)
-- Supabase SQL Editor에 그대로 붙여넣고 실행하세요.
-- (Storage 탭에서 "New bucket"으로 직접 만들어도 됩니다: 이름 "reports", Public 버킷으로 생성)

insert into storage.buckets (id, name, public)
values ('reports', 'reports', true)
on conflict (id) do nothing;

-- 업로드는 서버가 SUPABASE_SERVICE_KEY(관리자 권한)로만 수행하므로 별도 쓰기 정책은 필요 없습니다.
-- 다만 명시적으로 공개 읽기 정책도 추가해둡니다 (버킷이 public이면 사실 없어도 동작합니다).
drop policy if exists "Public read for reports bucket" on storage.objects;
create policy "Public read for reports bucket"
on storage.objects for select
using (bucket_id = 'reports');
