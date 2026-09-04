-- SaveMap 데모용 샘플 데이터 (평택 지역)
-- Supabase SQL Editor에 그대로 붙여넣고 실행하세요.
-- source/layer/category enum 값은 app/domain/enums.py 와 동일해야 합니다.
-- 참고: FLASH(타임세일) 레이어는 MVP 검색(rule_filter, mvp_only=True)에서
-- 의도적으로 제외되므로(원래 설계상 마감세일은 제보 위주), 지도 검색 결과에서
-- 바로 확인 가능하도록 이 데모는 core_base/regular 레이어만 사용합니다.

BEGIN;

-- 1) 평택시청 공영주차장 - 무료주차 (공공데이터, 상시)
WITH p1 AS (
  INSERT INTO place (name, address, geom)
  VALUES ('평택시청 공영주차장', '경기 평택시 중앙로 41',
          ST_SetSRID(ST_MakePoint(127.1125, 36.9928), 4326))
  RETURNING id
)
INSERT INTO offer (place_id, source, layer, category, title)
SELECT id, 'S1_PUBLIC', 'CORE_BASE', 'FREE_PARKING', '평일 18시 이후 무료' FROM p1;

-- 2) 평택역 국민도서관 - 무료 열람실 (공공데이터, 상시)
WITH p2 AS (
  INSERT INTO place (name, address, geom)
  VALUES ('평택시립도서관', '경기 평택시 평택동',
          ST_SetSRID(ST_MakePoint(127.1103, 36.9945), 4326))
  RETURNING id
)
INSERT INTO offer (place_id, source, layer, category, title)
SELECT id, 'S1_PUBLIC', 'CORE_BASE', 'FREE', '무료 열람실 이용' FROM p2;

-- 3) 평택 중앙시장 정육점 - 상시 할인 (제휴/사업자)
WITH p3 AS (
  INSERT INTO place (name, address, geom)
  VALUES ('평택 중앙시장 늘푸른정육점', '경기 평택시 중앙시장로 12',
          ST_SetSRID(ST_MakePoint(127.1088, 36.9918), 4326))
  RETURNING id
)
INSERT INTO offer (place_id, source, layer, category, title, base_price, store_discount)
SELECT id, 'S3_MERCHANT', 'REGULAR', 'DISCOUNT', '삼겹살 200g 상시 20% 할인', 12000, 2400 FROM p3;

-- 4) 평택역 베이커리 - 마감 임박(데모용, 검색에 즉시 노출되도록 regular로 등록)
WITH p4 AS (
  INSERT INTO place (name, address, geom)
  VALUES ('평택역 베이커리', '경기 평택시 평택로 100',
          ST_SetSRID(ST_MakePoint(127.1129, 36.9920), 4326))
  RETURNING id
)
INSERT INTO offer (place_id, source, layer, category, title, base_price, store_discount)
SELECT id, 'S3_MERCHANT', 'REGULAR', 'CLOSING_SOON', '마감 임박 식빵 50% 할인', 8000, 4000 FROM p4;

-- 5) 평택 전통시장 - 지역화폐 가맹점 (공공데이터/온누리)
WITH p5 AS (
  INSERT INTO place (name, address, geom)
  VALUES ('평택 통복시장 청과물상회', '경기 평택시 통복시장로 8',
          ST_SetSRID(ST_MakePoint(127.1071, 36.9955), 4326))
  RETURNING id
)
INSERT INTO offer (place_id, source, layer, category, title, base_price, store_discount)
SELECT id, 'S1_PUBLIC', 'REGULAR', 'LOCAL_BENEFIT', '평택사랑상품권 6% 캐시백 가맹점', 10000, 0 FROM p5;

-- 6) 소사벌레포츠공원 공영주차장 - 무료주차
WITH p6 AS (
  INSERT INTO place (name, address, geom)
  VALUES ('소사벌레포츠공원 공영주차장', '경기 평택시 소사벌로 268',
          ST_SetSRID(ST_MakePoint(127.0951, 36.9878), 4326))
  RETURNING id
)
INSERT INTO offer (place_id, source, layer, category, title)
SELECT id, 'S1_PUBLIC', 'CORE_BASE', 'FREE_PARKING', '상시 무료 개방' FROM p6;

-- 7) 카페 무료 (예: 평택시 청년센터 카페)
WITH p7 AS (
  INSERT INTO place (name, address, geom)
  VALUES ('평택 청년카페 쉼표', '경기 평택시 평택3동',
          ST_SetSRID(ST_MakePoint(127.1140, 36.9902), 4326))
  RETURNING id
)
INSERT INTO offer (place_id, source, layer, category, title, base_price, store_discount)
SELECT id, 'S3_MERCHANT', 'REGULAR', 'DISCOUNT', '아메리카노 1+1', 4500, 4500 FROM p7;

-- 8) 안중 이마트 인근 (반경 밖 데이터 예시 - 다른 지역 확인용, 평택 시내에서 3km 밖)
WITH p8 AS (
  INSERT INTO place (name, address, geom)
  VALUES ('안중 로컬푸드 직매장', '경기 평택시 안중읍',
          ST_SetSRID(ST_MakePoint(126.9280, 36.9490), 4326))
  RETURNING id
)
INSERT INTO offer (place_id, source, layer, category, title, base_price, store_discount)
SELECT id, 'S1_PUBLIC', 'REGULAR', 'DISCOUNT', '지역 농산물 15% 할인', 15000, 2250 FROM p8;

COMMIT;

-- 확인
SELECT o.id AS offer_id, p.name, o.category, o.layer, o.title, o.base_price, o.store_discount
FROM offer o JOIN place p ON p.id = o.place_id
ORDER BY o.id;
