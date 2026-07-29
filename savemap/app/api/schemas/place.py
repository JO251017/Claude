from pydantic import BaseModel

from app.domain.enums import BusinessStatus


class MenuPriceComparisonResponse(BaseModel):
    menu_item_id: int
    name: str
    store_price: float
    region_average: float | None = None
    region_median: float | None = None
    sample_count: int
    savings_amount: float | None = None
    savings_rate: float | None = None
    reliable: bool


class StatusUpdateCreate(BaseModel):
    status: BusinessStatus
    lat: float
    lng: float
    accuracy_m: float | None = None


class StatusUpdateResponse(BaseModel):
    place_id: int
    status: BusinessStatus
    distance_m: float
    is_new_interest: bool
    interest_count: int
    xp_awarded: int
