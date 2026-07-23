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


class MissingReportImageError(SaveMapError):
    code = "SM4221"
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "제보는 이미지가 반드시 있어야 합니다"


class UnverifiedPaymentMethodError(SaveMapError):
    code = "SM4031"
    http_status = status.HTTP_403_FORBIDDEN
    message = "인증되지 않은 결제수단입니다"


class PartnerCircuitOpenError(SaveMapError):
    code = "SM5031"
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    message = "파트너 API 일시 차단 중입니다 (캐시 응답으로 폴백)"
