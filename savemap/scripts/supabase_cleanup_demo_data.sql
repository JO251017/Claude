-- SaveMap: 테스트용 데모 데이터 삭제 (주차장·도서관 등 음식점/카페가 아닌 가짜 데이터)
-- offer/menu_item/store_status_update/store_interest 등 연결된 데이터는 place 삭제 시
-- 전부 CASCADE로 함께 정리됩니다. 절약 인증(savings_certification) 기록은 삭제되지 않고
-- offer_id만 NULL로 남습니다 (사용자의 실제 인증 이력은 보존).
-- Supabase SQL Editor에서 실행해주세요.

DELETE FROM place WHERE name IN (
  '평택시청 공영주차장',
  '평택시립도서관',
  '평택 중앙시장 늘푸른정육점',
  '평택역 베이커리',
  '평택 통복시장 청과물상회',
  '소사벌레포츠공원 공영주차장',
  '평택 청년카페 쉼표',
  '안중 로컬푸드 직매장'
);

-- 확인 (0곳이어야 정상)
SELECT count(*) AS remaining_demo_places FROM place WHERE name IN (
  '평택시청 공영주차장',
  '평택시립도서관',
  '평택 중앙시장 늘푸른정육점',
  '평택역 베이커리',
  '평택 통복시장 청과물상회',
  '소사벌레포츠공원 공영주차장',
  '평택 청년카페 쉼표',
  '안중 로컬푸드 직매장'
);
