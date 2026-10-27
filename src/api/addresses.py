"""Buyer address book endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response

from src.auth import BuyerUser
from src.database import SessionDep
from src.errors import error_detail
from src.schemas.addresses import (
    AddressCreate,
    AddressDefault,
    AddressList,
    AddressResponse,
    AddressUpdate,
)
from src.services.addresses import AddressError, list_addresses, mutate_address

router = APIRouter(prefix="/addresses", tags=["Addresses"])
AddressID = Annotated[int, Path(gt=0)]


def change(session, buyer, action, body=None, address_id=None, version=None):
    try:
        return mutate_address(session, buyer.id, action, body, address_id, version)
    except AddressError as exc:
        raise HTTPException(exc.status, detail=error_detail(exc.code, exc.message)) from exc


@router.get("", response_model=AddressList)
def listing(buyer: BuyerUser, session: SessionDep):
    return AddressList(data=list_addresses(session, buyer.id))


@router.post("", response_model=AddressResponse, status_code=201)
def create(body: AddressCreate, buyer: BuyerUser, session: SessionDep):
    return AddressResponse(data=change(session, buyer, "create", body))


@router.put("/{address_id}", response_model=AddressResponse)
def edit(address_id: AddressID, body: AddressUpdate, buyer: BuyerUser, session: SessionDep):
    return AddressResponse(data=change(session, buyer, "update", body, address_id, body.version))


@router.patch("/{address_id}/default", response_model=AddressResponse)
def set_default(address_id: AddressID, body: AddressDefault, buyer: BuyerUser, session: SessionDep):
    return AddressResponse(
        data=change(session, buyer, "default", address_id=address_id, version=body.version)
    )


@router.delete("/{address_id}", status_code=204)
def remove(address_id: AddressID, buyer: BuyerUser, session: SessionDep):
    change(session, buyer, "delete", address_id=address_id)
    return Response(status_code=204)
