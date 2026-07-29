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


XP_REWARD: dict[XpReason, int] = {
    XpReason.VALID_REPORT: 20,
    XpReason.FIELD_VERIFICATION: 5,
    XpReason.SAVINGS_CERTIFIED: 10,
}

# 방문 상태 업데이트 / 영수증 인증은 고정 보상이 아니라 예상·실제 절약금액에 비례해
# 지급한다 (기획서 §11, §13). 배율만 여기 정의하고 실제 지급은 award_xp_amount()로 한다.
XP_MULTIPLIER: dict[XpReason, float] = {
    XpReason.STORE_VISIT_UPDATE: 1.0,
    XpReason.RECEIPT_VERIFIED: 3.0,
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
