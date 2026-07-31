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


# 1차: 매장 근처(50m)에서 "발견하기"만 눌러도 고정 보상 — 비교 데이터가 있어야만
# 보상이 나오던 예전 방식(예상 절약금액 비례)은 표본 부족 시 0XP가 돼 "찾아갈 이유"가
# 안 보이는 원인이었다. 2차: 영수증으로 실제 식사를 인증하면 1차의 3배.
XP_REWARD: dict[XpReason, int] = {
    XpReason.VALID_REPORT: 20,
    XpReason.FIELD_VERIFICATION: 5,
    XpReason.SAVINGS_CERTIFIED: 10,
    XpReason.STORE_VISIT_UPDATE: 5,
    XpReason.RECEIPT_VERIFIED: 15,
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
