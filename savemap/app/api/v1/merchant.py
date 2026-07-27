from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, UserDep
from app.api.schemas.merchant import (
    OfferCreate,
    OfferResponse,
    OfferUpdate,
    PlaceCreate,
    PlaceResponse,
)
from app.domain.offer import Offer
from app.domain.place import Place
from app.sources.merchant_console import service

router = APIRouter(tags=["merchant"], prefix="/merchant")


def _place_response(place: Place) -> PlaceResponse:
    return PlaceResponse(id=place.id, name=place.name, address=place.address)


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
    user_id: str = UserDep,
    session: AsyncSession = SessionDep,
) -> PlaceResponse:
    place = await service.create_place(
        session, user_id, payload.name, payload.address, payload.lat, payload.lng
    )
    return _place_response(place)


@router.get("/places", response_model=list[PlaceResponse])
async def list_places(
    user_id: str = UserDep,
    session: AsyncSession = SessionDep,
) -> list[PlaceResponse]:
    places = await service.list_places(session, user_id)
    return [_place_response(p) for p in places]


@router.post("/offers", response_model=OfferResponse, status_code=201)
async def create_offer(
    payload: OfferCreate,
    user_id: str = UserDep,
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
    user_id: str = UserDep,
    session: AsyncSession = SessionDep,
) -> list[OfferResponse]:
    offers = await service.list_offers(session, user_id)
    return [_offer_response(o) for o in offers]


@router.get("/offers/{offer_id}", response_model=OfferResponse)
async def get_offer(
    offer_id: int,
    user_id: str = UserDep,
    session: AsyncSession = SessionDep,
) -> OfferResponse:
    offer = await service.get_offer(session, user_id, offer_id)
    return _offer_response(offer)


@router.patch("/offers/{offer_id}", response_model=OfferResponse)
async def update_offer(
    offer_id: int,
    payload: OfferUpdate,
    user_id: str = UserDep,
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
    user_id: str = UserDep,
    session: AsyncSession = SessionDep,
) -> None:
    await service.delete_offer(session, user_id, offer_id)
