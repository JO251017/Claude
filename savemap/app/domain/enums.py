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


XP_REWARD: dict[XpReason, int] = {
    XpReason.VALID_REPORT: 20,
    XpReason.FIELD_VERIFICATION: 5,
}
