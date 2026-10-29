"""US16 integer-VND pricing (#135), with no database access or transaction effects.

The caller supplies selected cart snapshots and rules already checked for voucher
ownership, dates, minimums and usage limits by #133. Checkout (#136) owns that
validation, persistence and its single commit; this module only calculates money.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from src.services.order_errors import OrderError

BASIS_POINTS = 10_000
SHIPPING_FEE_VND = 20_000
PRICING_POLICY_VERSION = "US16-V1"


class PricingError(OrderError):
    """A pricing business rejection, distinct from invalid calculation input."""


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


def calculate_item_discount(rule: ItemDiscount, basis: int) -> int:
    """Floor percentages, then cap by the configured maximum and the item basis."""
    _check_integer(basis, "basis")
    if rule.discount_type == "FIXED_AMOUNT":
        return min(basis, rule.discount_value)
    discount = basis * rule.discount_value // BASIS_POINTS
    if rule.max_discount is not None:
        discount = min(discount, rule.max_discount)
    return min(discount, basis)


def allocate_platform_discount(discount: int, bases: Mapping[int, int]) -> dict[int, int]:
    """Use largest remainders; equal remainders prefer the smaller seller ID."""
    _check_integer(discount, "discount")
    for seller_id, basis in bases.items():
        _check_integer(seller_id, "seller_id", 1)
        _check_integer(basis, "basis")
    total_basis = sum(bases.values())
    if discount > total_basis:
        raise ValueError("Platform discount must not exceed the total post-shop basis.")
    if total_basis == 0:
        return dict.fromkeys(sorted(bases), 0)

    shares = {
        seller_id: divmod(discount * bases[seller_id], total_basis) for seller_id in sorted(bases)
    }
    allocated = {seller_id: quotient for seller_id, (quotient, _) in shares.items()}
    remaining = discount - sum(allocated.values())
    ranked = sorted(
        (seller_id for seller_id in bases if bases[seller_id] > 0),
        key=lambda seller_id: (-shares[seller_id][1], seller_id),
    )
    for seller_id in ranked[:remaining]:
        allocated[seller_id] += 1
    return allocated


def _applied_item_discount(rule: ItemDiscount | None, basis: int, slot: str) -> int:
    if rule is None:
        return 0
    discount = calculate_item_discount(rule, basis)
    if discount == 0:
        raise PricingError(
            "ERR_VOUCHER_NOT_APPLICABLE", f"The {slot} voucher yields zero item discount."
        )
    return discount


def _shipping_discount_amount(rule: ShippingDiscount | None) -> int:
    if rule is None:
        return 0
    cap = SHIPPING_FEE_VND if rule.max_discount is None else rule.max_discount
    return min(SHIPPING_FEE_VND, cap)


def price_order(
    lines: Iterable[PricingLine],
    *,
    shop_discounts: Mapping[int, ItemDiscount] | None = None,
    platform_discount: ItemDiscount | None = None,
    shipping_discount: ShippingDiscount | None = None,
) -> OrderPrice:
    """Price selected lines in shop -> platform -> shipping order without side effects.

    Stable seller ordering and immutable results make the same snapshots yield
    the same price for quote and transactional checkout. This does not authorize
    a voucher, consume it, or re-price any historical order.
    """
    subtotals: dict[int, int] = {}
    for line in lines:
        subtotals[line.seller_id] = (
            subtotals.get(line.seller_id, 0) + line.quantity * line.unit_price
        )
    if not subtotals:
        raise PricingError("ERR_EMPTY_CART", "Select at least one item for checkout.", 400)

    shop_rules = dict(shop_discounts or {})
    for seller_id in shop_rules:
        _check_integer(seller_id, "seller_id", 1)
        if seller_id not in subtotals:
            raise ValueError("Shop discount seller must have selected lines in this order.")
    shop_amounts = {
        seller_id: _applied_item_discount(shop_rules.get(seller_id), subtotal, "shop")
        for seller_id, subtotal in subtotals.items()
    }
    bases = {
        seller_id: subtotal - shop_amounts[seller_id] for seller_id, subtotal in subtotals.items()
    }
    platform_amount = _applied_item_discount(platform_discount, sum(bases.values()), "platform")
    platform_amounts = allocate_platform_discount(platform_amount, bases)
    if sum(platform_amounts.values()) != platform_amount:
        # Keep the guard enabled under python -O; a broken allocation is an internal fault.
        raise RuntimeError("Platform discount allocation must conserve money.")

    shipping_amount = _shipping_discount_amount(shipping_discount)
    seller_orders = tuple(
        SellerOrderPrice(
            seller_id=seller_id,
            subtotal=subtotals[seller_id],
            shop_discount=shop_amounts[seller_id],
            platform_discount=platform_amounts[seller_id],
            shipping_fee=SHIPPING_FEE_VND,
            shipping_discount=shipping_amount,
            total_amount=(
                bases[seller_id] - platform_amounts[seller_id] + SHIPPING_FEE_VND - shipping_amount
            ),
        )
        for seller_id in sorted(subtotals)
    )
    return OrderPrice(
        seller_orders=seller_orders,
        subtotal=sum(row.subtotal for row in seller_orders),
        shop_discount=sum(row.shop_discount for row in seller_orders),
        platform_discount=platform_amount,
        shipping_fee=sum(row.shipping_fee for row in seller_orders),
        shipping_discount=sum(row.shipping_discount for row in seller_orders),
        grand_total=sum(row.total_amount for row in seller_orders),
    )
