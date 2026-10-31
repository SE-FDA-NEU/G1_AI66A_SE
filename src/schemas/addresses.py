"""Strict public contracts for the buyer address book."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from src.schemas.delivery import normalize_phone, valid_phone, visible_text

PositiveID = Annotated[int, Field(strict=True, gt=0)]


class AddressCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recipient_name: str = Field(min_length=1, max_length=100)
    phone_number: str = Field(min_length=7, max_length=20)
    province: str = Field(min_length=1, max_length=100)
    district: str = Field(min_length=1, max_length=100)
    ward: str = Field(min_length=1, max_length=100)
    detailed_address: str = Field(min_length=1, max_length=500)
    is_default: StrictBool = False

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, value: str) -> str:
        return normalize_phone(valid_phone(value))
    _visible = field_validator(
        "recipient_name", "province", "district", "ward", "detailed_address"
    )(visible_text)


class AddressUpdate(AddressCreate):
    version: PositiveID


class AddressDefault(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: PositiveID


class AddressData(AddressCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version: int
    created_at: datetime
    updated_at: datetime


class AddressResponse(BaseModel):
    data: AddressData


class AddressList(BaseModel):
    data: list[AddressData]


def delivery_validation_errors(errors: list[dict], body: object, checkout: bool) -> dict:
    """Hide union branch names and raw inputs while retaining actionable field messages."""
    fields: dict[str, list[str]] = {}
    branch = (
        "SavedAddressCheckoutRequest"
        if isinstance(body, dict) and ("address_id" in body or "address_version" in body)
        else "CheckoutRequest"
    )
    allowed = set(AddressCreate.model_fields) | {"version"}
    if checkout:
        allowed = (
            {"address_id", "address_version"}
            if branch.startswith("Saved")
            else {"recipient_name", "phone_number", "delivery_address"}
        )
    for error in errors:
        loc = error.get("loc", ())
        if (
            checkout
            and len(loc) > 1
            and loc[1] in ("CheckoutRequest", "SavedAddressCheckoutRequest")
            and loc[1] != branch
        ):
            continue
        name = str(loc[-1]) if loc else "_form"
        if name not in allowed or error["type"] in ("extra_forbidden", "json_invalid"):
            name = "_form"
        message = error["msg"].removeprefix("Value error, ")
        if name == "phone_number":
            message = (
                "Phone number must contain 7 to 15 digits. "
                "Use only +, spaces, (), or - as separators."
            )
        elif error["type"] == "missing" and name != "_form":
            message = f"Enter {name.replace('_', ' ')}."
        elif error["type"] == "string_too_short":
            message = "Enter this required field using visible text."
        elif name == "_form":
            message = "Send one supported request object with only the allowed fields."
        fields.setdefault(name, []).append(message)
    return {
        "error": {
            "code": "ERR_VALIDATION",
            "message": "Please correct the highlighted fields.",
            "fields": fields,
        }
    }
