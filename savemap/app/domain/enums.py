import enum


class SourceType(str, enum.Enum):
    S1_PUBLIC = "s1_public"
    S2_PARTNER = "s2_partner"
    S3_MERCHANT = "s3_merchant"
    S4_REPORT = "s4_report"
    S5_VERIFICATION = "s5_verification"


SOURCE_PRIORITY: dict[SourceType, int] = {
    SourceType.S1_PUBLIC: 1,
    SourceType.S2_PARTNER: 2,
    SourceType.S3_MERCHANT: 3,
    SourceType.S4_REPORT: 4,
    SourceType.S5_VERIFICATION: 5,
}


class Layer(str, enum.Enum):
    CORE_BASE = "core_base"
    REGULAR = "regular"
    FLASH = "flash"


class Category(str, enum.Enum):
    FREE = "free"
    DISCOUNT = "discount"
    CLOSING_SOON = "closing_soon"
    FREE_PARKING = "free_parking"
    LOCAL_BENEFIT = "local_benefit"


class PaymentMethodType(str, enum.Enum):
    CARD = "card"
    TELCO = "telco"
    LOCAL_CURRENCY = "local_currency"


# AI 절약 플랜에서 사용자가 실제로 고르는 건 "할인/무료/마감세일"(=Category, 절약
# 수단) 이 아니라 "뭘 하고 싶은지"다 — 이 둘을 데이터 모델에서부터 분리한다
# (사용자 지시, 2026-08-13). Category는 여전히 존재하고 그대로 쓰이지만, 이제
# "SaveMap이 내부적으로 자동 탐색하는 절약 수단"이지 사용자가 직접 고르는 1차
# 선택지가 아니다. Activity는 Place.category_name(공공데이터/카카오가 준 실제
# 업종 문자열)에서 키워드로 매핑 가능한 것만 우선 넣는다(app/engine/activity_classifier.py) —
# 매핑 근거가 없는 "쇼핑"/"문화·여가"/"가족활동"은 지금 데이터로는 지어낼 수
# 없으므로 이번엔 넣지 않는다.
class RouteActivity(str, enum.Enum):
    DINING = "dining"
    CAFE = "cafe"
    DESSERT = "dessert"


# AI 절약 플랜 Step2 "어떤 조건이 중요할까요?" — 단순 UI 장식이 아니라 build_route의
# 선택 순서(어떤 후보를 먼저 담을지)에 실제로 반영된다. 전부 이미 DB/계산엔진에 있는
# 실측값(가격/trust_score/last_verified_at/distance_m) 기반이라, 값이 없다고
# 임의로 채우지 않는다(예: trust_score 없으면 0.5 기본값 그대로 — 새로 지어내지 않음).
class RoutePreference(str, enum.Enum):
    CHEAPEST = "cheapest"  # 최대한 저렴하게
    VERIFIED = "verified"  # 검증된 정보 우선
    RECENT = "recent"  # 최신 정보 우선
    DISTANCE = "distance"  # 이동거리 최소화


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Verdict(str, enum.Enum):
    AVAILABLE = "available"
    SOLD_OUT = "sold_out"


class XpReason(str, enum.Enum):
    VALID_REPORT = "valid_report"
    FIELD_VERIFICATION = "field_verification"
    SAVINGS_CERTIFIED = "savings_certified"
    STORE_VISIT_UPDATE = "store_visit_update"
    RECEIPT_VERIFIED = "receipt_verified"
    MENU_REPORT = "menu_report"


# 1차: 매장 근처(50m)에서 "발견하기"만 눌러도 고정 보상 — 비교 데이터가 있어야만
# 보상이 나오던 예전 방식(예상 절약금액 비례)은 표본 부족 시 0XP가 돼 "찾아갈 이유"가
# 안 보이는 원인이었다. 2차: 영수증으로 실제 식사를 인증하면 1차의 3배.
# MENU_REPORT: 메뉴판 사진 제보로 그 매장에 "새로운" 메뉴 가격이 추가될 때만 지급
# (같은 메뉴 반복 제보로 XP를 캐지 못하도록).
XP_REWARD: dict[XpReason, int] = {
    XpReason.VALID_REPORT: 20,
    XpReason.FIELD_VERIFICATION: 5,
    XpReason.SAVINGS_CERTIFIED: 10,
    XpReason.STORE_VISIT_UPDATE: 5,
    XpReason.RECEIPT_VERIFIED: 15,
    XpReason.MENU_REPORT: 10,
}


class BusinessStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    TEMP_CLOSED = "temp_closed"
    UNKNOWN = "unknown"


class CertificationMethod(str, enum.Enum):
    SIMPLE = "simple"
    RECEIPT = "receipt"


class CertificationConfidence(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


CERTIFICATION_CONFIDENCE: dict[CertificationMethod, CertificationConfidence] = {
    CertificationMethod.RECEIPT: CertificationConfidence.HIGH,
    CertificationMethod.SIMPLE: CertificationConfidence.MEDIUM,
}


class AssetStatus(str, enum.Enum):
    AVAILABLE = "available"
    EXCHANGED = "exchanged"
