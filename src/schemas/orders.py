"""Checkout contracts; money is integer VND and items come from the buyer cart."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.addresses import PositiveID
from src.schemas.delivery import valid_phone, visible_text
from src.schemas.order_history import OrderHistoryEntry

VoucherCode = Annotated[str, Field(min_length=1, max_length=32)]
PaymentMethod = Literal["COD", "VIETQR", "WALLET", "CARD"]


class ShopVoucherCode(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    seller_id: PositiveID
    code: VoucherCode


class VoucherSelection(BaseModel):
    """US16 section 5.1: the codes a buyer asks to apply; every field optional."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    shop_vouchers: list[ShopVoucherCode] = Field(default_factory=list, max_length=50)
    platform_voucher: VoucherCode | None = None
    shipping_voucher: VoucherCode | None = None

    @field_validator("shop_vouchers")
    @classmethod
    def _one_voucher_per_shop(cls, value: list[ShopVoucherCode]) -> list[ShopVoucherCode]:
        if len({item.seller_id for item in value}) != len(value):
            raise ValueError("Apply at most one voucher per shop.")
        return value


class QuotedCheckout(VoucherSelection):
    """Checkout fields from US16 section 5.2; absent fields keep legacy pricing."""

    quote_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    # US20 section 3: absent means COD until the payment selector (#149) always sends it.
    payment_method: Literal["COD", "VIETQR", "WALLET", "CARD"] | None = None


class CheckoutRequest(QuotedCheckout):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recipient_name: str = Field(min_length=1, max_length=100)
    delivery_address: str = Field(min_length=1, max_length=1000)
    phone_number: str = Field(min_length=7, max_length=20)
    payment_method: PaymentMethod | None = None

    _phone = field_validator("phone_number")(valid_phone)
    _visible = field_validator("recipient_name", "delivery_address")(visible_text)


class SavedAddressCheckoutRequest(QuotedCheckout):
    model_config = ConfigDict(extra="forbid")
    address_id: PositiveID
    address_version: PositiveID
    payment_method: PaymentMethod | None = None


CheckoutInput = CheckoutRequest | SavedAddressCheckoutRequest


class DeliverySnapshot(BaseModel):
    recipient_name: str
    phone_number: str
    delivery_address: str


class SubOrderSummary(BaseModel):
    id: int
    seller_id: int
    status: str
    # null for orders placed before payment tracking (US20 section 10).
    payment_status: str | None = None
    escrow_status: str = "HELD"
    refunded_amount: int | None = None
    # Seller-scoped receipts only; never shown to the buyer.
    commission_amount: int | None = None
    seller_net_amount: int | None = None
    settled_at: datetime | None = None
    tracking_number: str | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None
    completed_at: datetime | None = None
    history: list[OrderHistoryEntry] = Field(default_factory=list)
    # Persisted US16 breakdown; LEGACY orders have no discounts or shipping.
    subtotal: int = 0
    shop_discount: int = 0
    platform_discount: int = 0
    shipping_fee: int = 0
    shipping_discount: int = 0
    total_amount: int = 0
    pricing_policy_version: str = "LEGACY"


class OrderLine(BaseModel):
    product_id: int
    variant_id: int | None = None
    # The receipt names each product; unit_price stays the purchase-time snapshot.
    product_code: str
    product_name: str
    variant_name: str | None = None
    image_url: str | None = None
    seller_order_id: int
    quantity: int
    unit_price: int
    line_total: int
    seller_order_status: str | None = None


class AppliedVoucher(BaseModel):
    code: str
    slot: str
    seller_order_id: int | None = None
    discount_amount: int
    status: str


class OrderData(BaseModel):
    id: int
    status: str
    total_amount: int
    recipient_name: str
    delivery_address: str
    phone_number: str
    payment_status: str | None = None
    payment_method: PaymentMethod | None = None

    escrow_status: str = "HELD"
    paid_amount: int | None = None
    refunded_amount: int | None = None
    created_at: datetime
    tracking_number: str | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None
    completed_at: datetime | None = None
    items: list[OrderLine]
    sub_orders: list[SubOrderSummary] = Field(default_factory=list)
    vouchers: list[AppliedVoucher] = Field(default_factory=list)


class OrderResponse(BaseModel):
    data: OrderData


class VoucherResult(BaseModel):
    code: str
    status: str
    discount: int = 0
    error: dict[str, str] | None = None


class QuoteSellerOrder(BaseModel):
    seller_id: int
    items: list[dict[str, int | None]]
    subtotal: int
    shop_discount: int
    platform_discount: int
    shipping_fee: int
    shipping_discount: int
    total_amount: int
    shop_voucher: VoucherResult | None = None


class CheckoutQuote(BaseModel):
    currency: str = "VND"
    pricing_policy_version: str
    quote_revision: str
    seller_orders: list[QuoteSellerOrder]
    platform_voucher: VoucherResult | None = None
    shipping_voucher: VoucherResult | None = None
    subtotal: int
    shop_discount: int
    platform_discount: int
    shipping_fee: int
    shipping_discount: int
    grand_total: int


class QuoteResponse(BaseModel):
    data: CheckoutQuote
