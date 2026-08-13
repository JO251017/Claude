from fastapi import HTTPException, status


class SaveMapError(HTTPException):
    code: str = "SM0000"

    def __init__(self, detail: str | None = None):
        super().__init__(status_code=self.http_status, detail={"code": self.code, "message": detail or self.message})

    http_status: int = status.HTTP_400_BAD_REQUEST
    message: str = "SaveMap error"


class MissingCoordinatesError(SaveMapError):
    code = "SM4001"
    http_status = status.HTTP_400_BAD_REQUEST
    message = "위도/경도가 필요합니다"


class RadiusOutOfRangeError(SaveMapError):
    code = "SM4002"
    http_status = status.HTTP_400_BAD_REQUEST
    message = "검색 반경이 허용 범위를 벗어났습니다"


class BudgetOutOfRangeError(SaveMapError):
    code = "SM4003"
    http_status = status.HTTP_400_BAD_REQUEST
    message = "예산이 허용 범위를 벗어났습니다"


class MissingReportImageError(SaveMapError):
    code = "SM4221"
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    message = "제보는 이미지가 반드시 있어야 합니다"


class ReportImageFetchError(SaveMapError):
    code = "SM4222"
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    message = "사진을 불러올 수 없습니다. 이미지 주소를 다시 확인해주세요"


class OcrServiceError(SaveMapError):
    code = "SM5033"
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    message = "사진 분석 서비스에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해주세요"


class AuthenticationRequiredError(SaveMapError):
    code = "SM4011"
    http_status = status.HTTP_401_UNAUTHORIZED
    message = "로그인이 필요한 기능입니다"


class UnverifiedPaymentMethodError(SaveMapError):
    code = "SM4031"
    http_status = status.HTTP_403_FORBIDDEN
    message = "인증되지 않은 결제수단입니다"


class MerchantNotVerifiedError(SaveMapError):
    code = "SM4032"
    http_status = status.HTTP_403_FORBIDDEN
    message = "사업자 인증이 필요한 기능입니다"


class PartnerCircuitOpenError(SaveMapError):
    code = "SM5031"
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    message = "파트너 API 일시 차단 중입니다 (캐시 응답으로 폴백)"


class PlaceNotFoundError(SaveMapError):
    code = "SM4041"
    http_status = status.HTTP_404_NOT_FOUND
    message = "매장을 찾을 수 없거나 소유하고 있지 않습니다"


class OfferNotFoundError(SaveMapError):
    code = "SM4042"
    http_status = status.HTTP_404_NOT_FOUND
    message = "혜택을 찾을 수 없거나 소유하고 있지 않습니다"


class OfferPublicNotFoundError(SaveMapError):
    code = "SM4043"
    http_status = status.HTTP_404_NOT_FOUND
    message = "혜택을 찾을 수 없습니다"


class CertificationNotSupportedError(SaveMapError):
    code = "SM4223"
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    message = "이 혜택은 절약 인증을 지원하지 않습니다 (가격 정보 없음)"


class AssetNotFoundError(SaveMapError):
    code = "SM4044"
    http_status = status.HTTP_404_NOT_FOUND
    message = "절약 자산을 찾을 수 없거나 소유하고 있지 않습니다"


class ImageUploadError(SaveMapError):
    code = "SM5034"
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    message = "사진 업로드에 실패했습니다. 잠시 후 다시 시도해주세요"


class InvalidImageError(SaveMapError):
    code = "SM4224"
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    message = "올바른 이미지 파일이 아닙니다"


class TooFarFromStoreError(SaveMapError):
    code = "SM4225"
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    message = "매장에서 너무 멀리 떨어져 있습니다 (50m 이내에서만 방문 인증이 가능합니다)"


class LowGpsAccuracyError(SaveMapError):
    code = "SM4226"
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    message = "GPS 정확도가 낮아 위치를 확인할 수 없습니다. 실외에서 다시 시도해주세요"


class PlacePublicNotFoundError(SaveMapError):
    code = "SM4045"
    http_status = status.HTTP_404_NOT_FOUND
    message = "매장을 찾을 수 없습니다"


class MenuItemNotFoundError(SaveMapError):
    code = "SM4046"
    http_status = status.HTTP_404_NOT_FOUND
    message = "메뉴를 찾을 수 없거나 소유하고 있지 않습니다"


class InvalidCsvError(SaveMapError):
    code = "SM4225"
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    message = "올바른 CSV 파일이 아닙니다"


class PlaceMenuAlreadyRegisteredError(SaveMapError):
    """오픈된 커뮤니티 메뉴 제보 경로(/places/menu-reports)는 사업자 인증 없이 로그인만
    하면 누구나 쓸 수 있다 — 그래서 한 매장은 최초 1건만 등록되게 막는다(사용자 지시,
    2026-08-13: "한번 등록되면 일단 추가 등록은 안되게해"). 프론트가 이미 가격 정보
    없는 매장에서만 이 흐름을 보여주므로 보통 걸릴 일은 없고, 두 사용자가 거의 동시에
    같은 매장을 제보하는 경쟁 상황을 막는 서버 사이드 안전장치 역할이 크다. 사업자
    콘솔(소유권 확인된 경로)은 이 제한과 무관하다."""

    code = "SM4227"
    http_status = status.HTTP_409_CONFLICT
    message = "이미 메뉴 정보가 등록된 매장이에요. 사업자이시면 사업자 콘솔에서 수정해주세요"
