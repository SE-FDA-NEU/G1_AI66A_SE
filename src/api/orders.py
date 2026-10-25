"""Buyer checkout and confirmation API."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response

from src.auth import BuyerUser
from src.database import SessionDep
from src.errors import error_detail
from src.schemas.orders import CheckoutInput, OrderResponse
from src.services.orders import CheckoutError, checkout, receipt

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("", response_model=OrderResponse, status_code=201)
def place_order(
    body: CheckoutInput,
    buyer: BuyerUser,
    session: SessionDep,
    response: Response,
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=64)],
) -> OrderResponse:
    if not key.strip() or key != key.strip():
        raise HTTPException(400, detail=error_detail("ERR_INVALID_KEY", "Invalid idempotency key."))
    try:
        data, created = checkout(session, buyer.id, body, key)
        response.status_code = 201 if created else 200
        return OrderResponse(data=data)
    except CheckoutError as exc:
        raise HTTPException(exc.status, detail=error_detail(exc.code, exc.message)) from exc


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, buyer: BuyerUser, session: SessionDep) -> OrderResponse:
    try:
        return OrderResponse(data=receipt(session, buyer.id, order_id))
    except CheckoutError as exc:
        raise HTTPException(exc.status, detail=error_detail(exc.code, exc.message)) from exc
