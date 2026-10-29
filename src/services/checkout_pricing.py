"""US16 quote and checkout pricing over the buyer's selected cart (#136).

Quote and checkout call the same functions, so the price a buyer reviews is the price
checkout charges. Nothing here writes, flushes or commits: checkout owns the transaction
and consumes vouchers itself (docs/us16-promotions.md sections 5 and 7).
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlmodel import Session, select

from src.models.cart_item import CartItem
from src.models.product import Product
from src.models.product_variant import ProductVariant
from src.models.voucher import Voucher
from src.schemas.orders import (
    CheckoutQuote,
    QuoteSellerOrder,
    VoucherResult,
    VoucherSelection,
)
from src.services.order_errors import OrderError
from src.services.pricing import (
    PRICING_POLICY_VERSION,
    SHIPPING_FEE_VND,
    ItemDiscount,
    OrderPrice,
    PricingLine,
    ShippingDiscount,
    price_order,
)
from src.services.vouchers import VoucherError, normalize_voucher_code, validate_voucher


class QuoteError(OrderError):
    """A rejected quote or a stale/ineligible voucher at checkout."""

    def __init__(self, code: str, message: str, status: int = 409, *, field: str | None = None):
        super().__init__(code, message, status)
        self.field = field


@dataclass(frozen=True)
class SelectedLine:
    product_id: int
    variant_id: int | None
    seller_id: int
    quantity: int
    unit_price: int
    is_active: bool


@dataclass
class AppliedVouchers:
    """Vouchers that passed eligibility, with the slot each one fills."""

    shop: dict[int, Voucher] = field(default_factory=dict)
    platform: Voucher | None = None
    shipping: Voucher | None = None


@dataclass
class PricedSelection:
    lines: list[SelectedLine]
    price: OrderPrice
    applied: AppliedVouchers
    results: dict[str, VoucherResult]
    revision: str


def selected_lines(session: Session, buyer_id: int) -> list[SelectedLine]:
    """Current prices of the selected cart lines; the client never supplies a price."""
    lines = []
    cart = session.exec(
        select(CartItem)
        .where(CartItem.buyer_id == buyer_id, CartItem.is_selected.is_(True))
        .order_by(CartItem.product_id, CartItem.id)
    ).all()
    for item in cart:
        product = session.get(Product, item.product_id)
        variant = session.get(ProductVariant, item.variant_id) if item.variant_id else None
        if product is None or (item.variant_id is not None and variant is None):
            raise QuoteError(
                "ERR_PRODUCT_UNAVAILABLE", f"Product {item.product_id} is no longer available."
            )
        stock = variant or product
        lines.append(
            SelectedLine(
                product_id=product.id,
                variant_id=item.variant_id,
                seller_id=product.seller_id,
                quantity=item.quantity,
                unit_price=stock.price,
                is_active=product.is_active and stock.is_active,
            )
        )
    if not lines:
        raise QuoteError("ERR_EMPTY_CART", "Select at least one item for checkout.", 400)
    return lines


def _slot_key(slot: str, seller_id: int | None = None) -> str:
    """The `error.fields` names from US16 section 5.2."""
    return f"shop_vouchers.{seller_id}" if slot == "SHOP" else f"{slot.lower()}_voucher"


def _item_rule(voucher: Voucher) -> ItemDiscount:
    return ItemDiscount(voucher.discount_type, voucher.discount_value, voucher.max_discount)


def _rule_fields(voucher: Voucher) -> list:
    return [
        voucher.code,
        voucher.scope,
        voucher.seller_id,
        voucher.discount_type,
        voucher.discount_value,
        voucher.max_discount,
        voucher.min_order_value,
        voucher.starts_at.isoformat(),
        voucher.ends_at.isoformat(),
        voucher.is_active,
    ]


def _revision(
    buyer_id: int,
    lines: list[SelectedLine],
    selection: VoucherSelection,
    rules: dict[str, Voucher | None],
) -> str:
    """SHA-256 of the price inputs (section 5.3); stock and usage counters are excluded."""
    payload = {
        "buyer_id": buyer_id,
        "policy": PRICING_POLICY_VERSION,
        "shipping_fee": SHIPPING_FEE_VND,
        "lines": [
            [line.product_id, line.variant_id, line.quantity, line.unit_price, line.is_active]
            for line in lines
        ],
        # Only the voucher fields: a checkout body also carries delivery data.
        "requested": selection.model_dump(mode="json", include=set(VoucherSelection.model_fields)),
        # Rules of every requested code, eligible or not: an exhausted usage limit
        # is reported with its own error code, not as a stale quote.
        "rules": {key: _rule_fields(v) if v else None for key, v in sorted(rules.items())},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def price_selection(
    session: Session,
    buyer_id: int,
    selection: VoucherSelection,
    *,
    now: datetime | None = None,
) -> PricedSelection:
    """Validate each requested voucher in slot order, then price what stays eligible.

    An ineligible voucher is reported as REJECTED and the rest is still priced, as the
    quote shows it. Checkout then calls `require_applied` to abort instead.
    """
    now = now or datetime.now(UTC)
    lines = selected_lines(session, buyer_id)
    subtotals: dict[int, int] = {}
    for line in lines:
        subtotals[line.seller_id] = subtotals.get(line.seller_id, 0) + (
            line.quantity * line.unit_price
        )
    applied = AppliedVouchers()
    results: dict[str, VoucherResult] = {}

    rules: dict[str, Voucher | None] = {}

    def check(code: str, slot: str, basis: int, *, seller_id=None, shipping_fee=0):
        key = _slot_key(slot, seller_id)
        rules[key] = session.exec(
            select(Voucher).where(Voucher.code == normalize_voucher_code(code))
        ).first()
        try:
            if slot == "SHOP" and seller_id not in subtotals:
                raise VoucherError(
                    "ERR_VOUCHER_SCOPE_MISMATCH",
                    f"No selected item belongs to seller {seller_id}.",
                )
            voucher, discount = validate_voucher(
                session,
                code,
                slot=slot,
                basis=basis,
                seller_id=seller_id,
                buyer_id=buyer_id,
                shipping_fee=shipping_fee,
                now=now,
            )
        except VoucherError as exc:
            results[key] = VoucherResult(
                code=code, status="REJECTED", error={"code": exc.code, "message": exc.message}
            )
            return None
        results[key] = VoucherResult(code=voucher.code, status="APPLIED", discount=discount)
        return voucher

    for item in selection.shop_vouchers:
        voucher = check(
            item.code, "SHOP", subtotals.get(item.seller_id, 0), seller_id=item.seller_id
        )
        if voucher is not None:
            applied.shop[item.seller_id] = voucher

    shop_price = price_order(
        [PricingLine(line.seller_id, line.quantity, line.unit_price) for line in lines],
        shop_discounts={s: _item_rule(v) for s, v in applied.shop.items()},
    )
    platform_basis = shop_price.subtotal - shop_price.shop_discount
    if selection.platform_voucher:
        applied.platform = check(selection.platform_voucher, "PLATFORM", platform_basis)
    if selection.shipping_voucher:
        applied.shipping = check(
            selection.shipping_voucher,
            "SHIPPING",
            platform_basis,
            shipping_fee=shop_price.shipping_fee,
        )

    price = price_order(
        [PricingLine(line.seller_id, line.quantity, line.unit_price) for line in lines],
        shop_discounts={s: _item_rule(v) for s, v in applied.shop.items()},
        platform_discount=_item_rule(applied.platform) if applied.platform else None,
        shipping_discount=(
            ShippingDiscount(applied.shipping.max_discount) if applied.shipping else None
        ),
    )
    # The calculator applies the amounts; report those, not the validator's estimate.
    for row in price.seller_orders:
        if row.seller_id in applied.shop:
            results[_slot_key("SHOP", row.seller_id)].discount = row.shop_discount
    if applied.platform:
        results["platform_voucher"].discount = price.platform_discount
    if applied.shipping:
        results["shipping_voucher"].discount = price.shipping_discount
    return PricedSelection(
        lines=lines,
        price=price,
        applied=applied,
        results=results,
        revision=_revision(buyer_id, lines, selection, rules),
    )


def require_applied(priced: PricedSelection) -> None:
    """Checkout aborts on the first rejected voucher in slot order (section 5.2 step 4)."""
    for key, result in priced.results.items():
        if result.status == "REJECTED":
            raise QuoteError(result.error["code"], result.error["message"], field=key)


def to_quote(priced: PricedSelection) -> CheckoutQuote:
    price = priced.price
    return CheckoutQuote(
        pricing_policy_version=price.pricing_policy_version,
        quote_revision=priced.revision,
        seller_orders=[
            QuoteSellerOrder(
                seller_id=row.seller_id,
                items=[
                    {
                        "product_id": line.product_id,
                        "variant_id": line.variant_id,
                        "quantity": line.quantity,
                        "unit_price": line.unit_price,
                    }
                    for line in priced.lines
                    if line.seller_id == row.seller_id
                ],
                subtotal=row.subtotal,
                shop_discount=row.shop_discount,
                platform_discount=row.platform_discount,
                shipping_fee=row.shipping_fee,
                shipping_discount=row.shipping_discount,
                total_amount=row.total_amount,
                shop_voucher=priced.results.get(_slot_key("SHOP", row.seller_id)),
            )
            for row in price.seller_orders
        ],
        platform_voucher=priced.results.get("platform_voucher"),
        shipping_voucher=priced.results.get("shipping_voucher"),
        subtotal=price.subtotal,
        shop_discount=price.shop_discount,
        platform_discount=price.platform_discount,
        shipping_fee=price.shipping_fee,
        shipping_discount=price.shipping_discount,
        grand_total=price.grand_total,
    )
