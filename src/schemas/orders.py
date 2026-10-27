"""Checkout contracts; money is integer VND and items come from the buyer cart."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.addresses import PositiveID
from src.schemas.delivery import valid_phone, visible_text


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recipient_name: str = Field(min_length=1, max_length=100)
    delivery_address: str = Field(min_length=1, max_length=1000)
    phone_number: str = Field(min_length=7, max_length=20)

    _phone = field_validator("phone_number")(valid_phone)
    _visible = field_validator("recipient_name", "delivery_address")(visible_text)


class SavedAddressCheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address_id: PositiveID
    address_version: PositiveID


CheckoutInput = CheckoutRequest | SavedAddressCheckoutRequest


class DeliverySnapshot(BaseModel):
    recipient_name: str
    phone_number: str
    delivery_address: str


class OrderLine(BaseModel):
    product_id: int
    # The receipt names each product; unit_price stays the purchase-time snapshot.
    product_code: str
    product_name: str
    seller_order_id: int
    quantity: int
    unit_price: int
    line_total: int


class OrderData(BaseModel):
    id: int
    status: str
    total_amount: int
    recipient_name: str
    delivery_address: str
    phone_number: str
    payment_status: str = "PAID"
    escrow_status: str = "HELD"
    created_at: datetime
    tracking_number: str | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None
    completed_at: datetime | None = None
    items: list[OrderLine]


class OrderResponse(BaseModel):
    data: OrderData
