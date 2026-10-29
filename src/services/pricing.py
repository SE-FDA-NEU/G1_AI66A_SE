"""US16 integer-VND pricing (#135), with no database access or transaction effects.

The caller supplies selected cart snapshots and rules already checked for voucher
ownership, dates, minimums and usage limits by #133. Checkout (#136) owns that
validation, persistence and its single commit; this module only calculates money.
"""

from dataclasses import dataclass
from typing import Literal

BASIS_POINTS = 10_000


SHIPPING_FEE_VND = 20_000


PRICING_POLICY_VERSION = "US16-V1"


class PricingError(ValueError):
    """A requested price cannot be produced; the controller maps code/status to HTTP."""

    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _check_integer(value: int, name: str, minimum: int = 0) -> None:
    # bool is an int subclass; accepting it here would silently price malformed input.
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}.")


@dataclass(frozen=True)
class PricingLine:
    seller_id: int
    quantity: int
    unit_price: int

    def __post_init__(self) -> None:
        _check_integer(self.seller_id, "seller_id", 1)
        _check_integer(self.quantity, "quantity", 1)
        _check_integer(self.unit_price, "unit_price")


@dataclass(frozen=True)
class ItemDiscount:
    """Calculation fields of an eligible shop/platform voucher; percentage is bps."""

    discount_type: Literal["FIXED_AMOUNT", "PERCENTAGE"]
    discount_value: int
    max_discount: int | None = None

    def __post_init__(self) -> None:
        if self.discount_type not in ("FIXED_AMOUNT", "PERCENTAGE"):
            raise ValueError("Item discount must be FIXED_AMOUNT or PERCENTAGE.")
        _check_integer(self.discount_value, "discount_value", 1)
        if self.discount_type == "PERCENTAGE" and self.discount_value > BASIS_POINTS:
            raise ValueError(f"Percentage must not exceed {BASIS_POINTS} basis points.")
        if self.max_discount is not None:
            _check_integer(self.max_discount, "max_discount", 1)
            if self.discount_type == "FIXED_AMOUNT":
                raise ValueError("max_discount only applies to percentage or shipping discounts.")


@dataclass(frozen=True)
class ShippingDiscount:
    """An eligible FREE_SHIPPING voucher's cap, applied to each seller order."""

    max_discount: int | None = None

    def __post_init__(self) -> None:
        if self.max_discount is not None:
            _check_integer(self.max_discount, "max_discount", 1)


@dataclass(frozen=True)
class SellerOrderPrice:
    seller_id: int
    subtotal: int
    shop_discount: int
    platform_discount: int
    shipping_fee: int
    shipping_discount: int
    total_amount: int
    pricing_policy_version: str = PRICING_POLICY_VERSION


@dataclass(frozen=True)
class OrderPrice:
    seller_orders: tuple[SellerOrderPrice, ...]
    subtotal: int
    shop_discount: int
    platform_discount: int
    shipping_fee: int
    shipping_discount: int
    grand_total: int
    pricing_policy_version: str = PRICING_POLICY_VERSION
