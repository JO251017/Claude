import uuid

from fastapi import APIRouter, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireMerchantVerifiedDep, SessionDep
from app.api.schemas.merchant import (
    MenuItemAnalyzeResponse,
    MenuItemCreate,
    MenuItemGuessItem,
    MenuItemResponse,
    MenuItemUpdate,
    OfferCreate,
    OfferResponse,
    OfferUpdate,
    PlaceCreate,
    PlaceResponse,
)
from app.core.errors import InvalidImageError
from app.domain.menu_item import MenuItem
from app.domain.offer import Offer
from app.domain.place import Place
from app.engine.price_comparison import MenuPriceComparison
from app.integrations.gemini import GeminiVisionClient
from app.integrations.supabase_storage import SupabaseStorageClient
from app.sources.merchant_console import service

router = APIRouter(tags=["merchant"], prefix="/merchant")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _place_response(place: Place) -> PlaceResponse:
    return PlaceResponse(id=place.id, name=place.name, address=place.address, phone=place.phone)


def _menu_item_response(
    item: MenuItem, cmp: MenuPriceComparison | None = None
) -> MenuItemResponse:
    return MenuItemResponse(
        id=item.id,
        place_id=item.place_id,
        name=item.name,
        price=float(item.price),
        source_url=item.source_url,
        verified_at=item.verified_at,
        region_median=cmp.region_median if cmp else None,
        sample_count=cmp.sample_count if cmp else 0,
        savings_amount=cmp.savings_amount if cmp else None,
        savings_rate=cmp.savings_rate if cmp else None,
        reliable=cmp.reliable if cmp else False,
        benchmark_source=cmp.benchmark_source if cmp else None,
        benchmark_price=cmp.benchmark_price if cmp else None,
        listed_on_map=bool(cmp and cmp.savings_amount and cmp.savings_amount > 0),
    )


def _offer_response(offer: Offer) -> OfferResponse:
    return OfferResponse(
        id=offer.id,
        place_id=offer.place_id,
        title=offer.title,
        category=offer.category,
        layer=offer.layer,
        base_price=offer.base_price,
        store_discount=offer.store_discount,
        valid_from=offer.valid_from,
        expires_at=offer.expires_at,
        ttl_sec=offer.ttl_sec,
    )


@router.post("/places", response_model=PlaceResponse, status_code=201)
async def create_place(
    payload: PlaceCreate,
    user_id: str = RequireMerchantVerifiedDep,
    session: AsyncSession = SessionDep,
) -> PlaceResponse:
    place = await service.create_place(
        session,
        user_id,
        payload.name,
        payload.address,
        payload.lat,
        payload.lng,
        phone=payload.phone,
        kakao_place_id=payload.kakao_place_id,
    )
    return _place_response(place)


@router.get("/places", response_model=list[PlaceResponse])
async def list_places(
    user_id: str = RequireMerchantVerifiedDep,
    session: AsyncSession = SessionDep,
) -> list[PlaceResponse]:
    places = await service.list_places(session, user_id)
    return [_place_response(p) for p in places]


@router.post("/offers", response_model=OfferResponse, status_code=201)
async def create_offer(
    payload: OfferCreate,
    user_id: str = RequireMerchantVerifiedDep,
    session: AsyncSession = SessionDep,
) -> OfferResponse:
    offer = await service.create_offer(
        session,
        user_id,
        place_id=payload.place_id,
        title=payload.title,
        category=payload.category,
        base_price=payload.base_price,
        store_discount=payload.store_discount,
        valid_from=payload.valid_from,
        expires_at=payload.expires_at,
        ttl_sec=payload.ttl_sec,
    )
    return _offer_response(offer)


@router.get("/offers", response_model=list[OfferResponse])
async def list_offers(
    user_id: str = RequireMerchantVerifiedDep,
    session: AsyncSession = SessionDep,
) -> list[OfferResponse]:
    offers = await service.list_offers(session, user_id)
    return [_offer_response(o) for o in offers]


@router.get("/offers/{offer_id}", response_model=OfferResponse)
async def get_offer(
    offer_id: int,
    user_id: str = RequireMerchantVerifiedDep,
    session: AsyncSession = SessionDep,
) -> OfferResponse:
    offer = await service.get_offer(session, user_id, offer_id)
    return _offer_response(offer)


@router.patch("/offers/{offer_id}", response_model=OfferResponse)
async def update_offer(
    offer_id: int,
    payload: OfferUpdate,
    user_id: str = RequireMerchantVerifiedDep,
    session: AsyncSession = SessionDep,
) -> OfferResponse:
    offer = await service.update_offer(
        session,
        user_id,
        offer_id,
        title=payload.title,
        base_price=payload.base_price,
        store_discount=payload.store_discount,
        expires_at=payload.expires_at,
        ttl_sec=payload.ttl_sec,
    )
    return _offer_response(offer)


@router.delete("/offers/{offer_id}", status_code=204)
async def delete_offer(
    offer_id: int,
    user_id: str = RequireMerchantVerifiedDep,
    session: AsyncSession = SessionDep,
) -> None:
    await service.delete_offer(session, user_id, offer_id)


@router.post("/menu-items/analyze", response_model=MenuItemAnalyzeResponse)
async def analyze_menu_photo(
    image: UploadFile = File(...),
    user_id: str = RequireMerchantVerifiedDep,
) -> MenuItemAnalyzeResponse:
    """메뉴판 사진 한 장에서 AI가 메뉴명·가격을 통째로 읽어온다. DB에는 저장하지
    않고(사용자 확인 전 단계), 확인 후에는 기존 메뉴 등록 API로 하나씩 저장한다."""
    content_type = image.content_type or ""
    if not content_type.startswith("image/"):
        raise InvalidImageError(f"이미지 파일이 아닙니다 (받은 형식: {content_type or '알 수 없음'})")

    content = await image.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise InvalidImageError("사진 용량이 너무 큽니다 (최대 10MB)")

    ext = (content_type.split("/")[-1] or "jpg").split(";")[0]
    path = f"{uuid.uuid4().hex}.{ext}"
    image_url = await SupabaseStorageClient().upload(path, content, content_type)

    guesses = await GeminiVisionClient().extract_menu_items(image_url)

    return MenuItemAnalyzeResponse(
        image_url=image_url,
        items=[MenuItemGuessItem(name=g.name, price=g.price) for g in guesses],
    )


@router.post("/menu-items", response_model=MenuItemResponse, status_code=201)
async def create_menu_item(
    payload: MenuItemCreate,
    user_id: str = RequireMerchantVerifiedDep,
    session: AsyncSession = SessionDep,
) -> MenuItemResponse:
    item, cmp = await service.create_menu_item(
        session,
        user_id,
        place_id=payload.place_id,
        name=payload.name,
        price=payload.price,
        source_url=payload.source_url,
    )
    return _menu_item_response(item, cmp)


@router.get("/places/{place_id}/menu-items", response_model=list[MenuItemResponse])
async def list_menu_items(
    place_id: int,
    user_id: str = RequireMerchantVerifiedDep,
    session: AsyncSession = SessionDep,
) -> list[MenuItemResponse]:
    items = await service.list_menu_items_for_owner(session, user_id, place_id)
    return [_menu_item_response(item, cmp) for item, cmp in items]


@router.patch("/menu-items/{menu_item_id}", response_model=MenuItemResponse)
async def update_menu_item(
    menu_item_id: int,
    payload: MenuItemUpdate,
    user_id: str = RequireMerchantVerifiedDep,
    session: AsyncSession = SessionDep,
) -> MenuItemResponse:
    item, cmp = await service.update_menu_item(
        session, user_id, menu_item_id, price=payload.price, source_url=payload.source_url
    )
    return _menu_item_response(item, cmp)


@router.delete("/menu-items/{menu_item_id}", status_code=204)
async def delete_menu_item(
    menu_item_id: int,
    user_id: str = RequireMerchantVerifiedDep,
    session: AsyncSession = SessionDep,
) -> None:
    await service.delete_menu_item(session, user_id, menu_item_id)
