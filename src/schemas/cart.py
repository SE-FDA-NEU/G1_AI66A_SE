"""Request and response schemas for the shopping cart (US03)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

PRODUCT_CODE_MAX_LENGTH = 20


class CartLineAvailability(StrEnum):
    """Whether a cart line can still be bought with its current quantity."""

    AVAILABLE = "available"
    INSUFFICIENT_STOCK = "insufficient_stock"
    UNAVAILABLE = "unavailable"


class AddCartItemRequest(BaseModel):
    """Body of `POST /api/v1/cart/items`."""

    product_code: str = Field(min_length=1, max_length=PRODUCT_CODE_MAX_LENGTH)
    # StrictInt refuses true, 1.5 and "2"; zero and negatives are left to the service.
    quantity: StrictInt


class UpdateCartItemRequest(BaseModel):
    """Body of `PATCH /api/v1/cart/items/{productCode}`."""

    quantity: StrictInt


class SelectCartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_selected: StrictBool


class CartLine(BaseModel):
    """One cart line, priced from the current product row."""

    cart_item_id: int
    seller_id: int
    seller_name: str
    is_selected: bool
    price_at_add: int
    price_changed: bool
    product_id: int
    product_code: str
    name: str
    image_url: str | None
    unit_price: int
    quantity: int
    line_total: int
    available_stock: int
    availability: CartLineAvailability


class Cart(BaseModel):
    """The buyer's whole cart; prices and totals are integer VND."""

    items: list[CartLine]
    cart_total: int
    selected_total: int
    supports_partial_checkout: bool = True


class CartResponse(BaseModel):
    """Envelope returned by every cart endpoint, for reads and mutations alike."""

    data: Cart
