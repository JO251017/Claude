-- SaveMap: 테스트용 데모 데이터 삭제 (주차장·도서관 등 음식점/카페가 아닌 가짜 데이터)
-- offer/menu_item/store_status_update/store_interest 등 연결된 데이터는 place 삭제 시
-- 전부 CASCADE로 함께 정리됩니다. 절약 인증(savings_certification) 기록은 삭제되지 않고
-- offer_id만 NULL로 남습니다 (사용자의 실제 인증 이력은 보존).
-- Supabase SQL Editor에서 실행해주세요.

-- 0) 실행 전: 지금 place 테이블에 실제로 뭐가 들어있는지 먼저 확인
SELECT id, name, address FROM place ORDER BY id;

-- 1) 데모 데이터 삭제 (이름 + 주소를 함께 매칭해서 실제로 등록한 매장과 절대 안 겹치게)
DELETE FROM place WHERE (name, address) IN (
  ('평택시청 공영주차장', '경기 평택시 중앙로 41'),
  ('평택시립도서관', '경기 평택시 평택동'),
  ('평택 중앙시장 늘푸른정육점', '경기 평택시 중앙시장로 12'),
  ('평택역 베이커리', '경기 평택시 평택로 100'),
  ('평택 통복시장 청과물상회', '경기 평택시 통복시장로 8'),
  ('소사벌레포츠공원 공영주차장', '경기 평택시 소사벌로 268'),
  ('평택 청년카페 쉼표', '경기 평택시 평택3동'),
  ('안중 로컬푸드 직매장', '경기 평택시 안중읍')
);

-- 2) 실행 후: 남은 전체 place 목록 (데모 8곳이 하나도 안 보여야 정상)
SELECT id, name, address FROM place ORDER BY id;
