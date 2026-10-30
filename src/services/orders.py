"""Atomic checkout and buyer-owned receipts (US04)."""

import hashlib
import time
from datetime import UTC, datetime

from sqlalchemy import delete, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, select

from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.product_variant import ProductVariant
from src.models.seller_order import SellerOrder
from src.models.voucher import Voucher
from src.models.voucher_usage import VoucherUsage
from src.schemas.order_history import order_timestamp_utc
from src.schemas.orders import (
    AppliedVoucher,
    CheckoutInput,
    CheckoutRequest,
    DeliverySnapshot,
    OrderData,
    OrderLine,
    SubOrderSummary,
)
from src.services.addresses import AddressError, owned_address
from src.services.checkout_pricing import (
    PricedSelection,
    QuoteError,
    price_selection,
    require_applied,
)
from src.services.notifications import create_notification
from src.services.order_errors import OrderError
from src.services.order_history import history_by_seller_order
from src.services.vouchers import VoucherError, consume_voucher


class CheckoutError(OrderError):
    """A checkout business rejection; retained here for existing callers."""


def receipt(
    session: Session,
    buyer_id: int | None,
    order_id: int,
    seller_id: int | None = None,
) -> OrderData:
    if seller_id is not None:
        sub_order = session.exec(
            select(SellerOrder).where(
                SellerOrder.order_id == order_id,
                SellerOrder.seller_id == seller_id,
            )
        ).first()
        if sub_order is None:
            raise CheckoutError("ERR_ORDER_NOT_FOUND", "Order not found.", 404)
        order = session.get(Order, order_id)
    elif buyer_id is not None:
        order = session.exec(
            select(Order).where(Order.id == order_id, Order.buyer_id == buyer_id)
        ).first()
    else:
        order = session.get(Order, order_id)
    if order is None:
        raise CheckoutError("ERR_ORDER_NOT_FOUND", "Order not found.", 404)
    item_query = (
        select(OrderItem, Product)
        .join(SellerOrder, SellerOrder.id == OrderItem.seller_order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(SellerOrder.order_id == order.id)
        .order_by(OrderItem.id)
    )
    if seller_id is not None:
        item_query = item_query.where(SellerOrder.seller_id == seller_id)
    rows = session.exec(item_query).all()
    values = order.model_dump(exclude={"buyer_id", "request_key", "request_hash"})
    values["created_at"] = order_timestamp_utc(order.created_at)
    if order.shipped_at:
        values["shipped_at"] = order_timestamp_utc(order.shipped_at)
    if order.delivered_at:
        values["delivered_at"] = order_timestamp_utc(order.delivered_at)
    if order.completed_at:
        values["completed_at"] = order_timestamp_utc(order.completed_at)
    sub_orders = session.exec(
        select(SellerOrder).where(SellerOrder.order_id == order.id).order_by(SellerOrder.id)
    ).all()
    sub_order_map = {so.id: so for so in sub_orders}
    visible_sub_orders = sub_orders
    if seller_id is not None:
        visible_sub_orders = [so for so in sub_orders if so.seller_id == seller_id]
        # The parent may carry another shop's latest tracking details.
        values["tracking_number"] = sub_order.tracking_number
        for milestone in ("shipped_at", "delivered_at", "completed_at"):
            timestamp = getattr(sub_order, milestone)
            values[milestone] = order_timestamp_utc(timestamp) if timestamp else None
    history = history_by_seller_order(session, [so.id for so in visible_sub_orders])

    return OrderData(
        **values,
        items=[
            OrderLine(
                **item.model_dump(),
                product_code=product.code,
                product_name=(
                    item.product_name_snapshot
                    if item.snapshot_initialized
                    else item.product_name_snapshot or product.name
                ),
                variant_name=item.variant_name_snapshot,
                image_url=(
                    item.product_image_snapshot
                    if item.snapshot_initialized
                    else item.product_image_snapshot or product.image_url
                ),
                line_total=item.quantity * item.unit_price,
                seller_order_status=sub_order_map[item.seller_order_id].status
                if item.seller_order_id in sub_order_map
                else None,
            )
            for item, product in rows
        ],
        sub_orders=[
            SubOrderSummary(
                id=so.id,  # type: ignore
                seller_id=so.seller_id,
                status=so.status,
                payment_status=so.payment_status,
                escrow_status=so.escrow_status,
                tracking_number=so.tracking_number,
                shipped_at=order_timestamp_utc(so.shipped_at) if so.shipped_at else None,
                delivered_at=order_timestamp_utc(so.delivered_at) if so.delivered_at else None,
                completed_at=order_timestamp_utc(so.completed_at) if so.completed_at else None,
                history=history.get(so.id, []),
                subtotal=so.subtotal,
                shop_discount=so.shop_discount,
                platform_discount=so.platform_discount,
                shipping_fee=so.shipping_fee,
                shipping_discount=so.shipping_discount,
                total_amount=so.total_amount,
                pricing_policy_version=so.pricing_policy_version,
            )
            for so in visible_sub_orders
            if so.id is not None
        ],
        vouchers=applied_vouchers(session, order.id, visible_sub_orders, seller_id),
    )


def applied_vouchers(
    session: Session,
    order_id: int,
    visible_sub_orders: list[SellerOrder],
    seller_id: int | None,
) -> list[AppliedVoucher]:
    """Codes read from stored usages; a seller sees only their own shop voucher."""
    visible_ids = {so.id for so in visible_sub_orders}
    rows = session.exec(
        select(VoucherUsage, Voucher)
        .join(Voucher, Voucher.id == VoucherUsage.voucher_id)
        .where(VoucherUsage.order_id == order_id)
        .order_by(VoucherUsage.id)
    ).all()
    return [
        AppliedVoucher(
            code=usage.code,
            slot=(
                "SHOP"
                if voucher.scope == "SHOP"
                else "SHIPPING"
                if voucher.discount_type == "FREE_SHIPPING"
                else "PLATFORM"
            ),
            seller_order_id=usage.seller_order_id,
            discount_amount=usage.discount_amount,
            status=usage.status,
        )
        for usage, voucher in rows
        if seller_id is None or usage.seller_order_id in visible_ids
    ]


def resolve_delivery_snapshot(
    session: Session, buyer_id: int, body: CheckoutInput
) -> DeliverySnapshot:
    if isinstance(body, CheckoutRequest):
        return DeliverySnapshot(**body.model_dump())
    try:
        address = owned_address(session, buyer_id, body.address_id, body.address_version)
    except AddressError as exc:
        raise CheckoutError(exc.code, exc.message, exc.status) from exc
    return DeliverySnapshot(
        recipient_name=address.recipient_name,
        phone_number=address.phone_number,
        delivery_address=", ".join(
            (address.detailed_address, address.ward, address.district, address.province)
        ),
    )


def apply_quoted_price(
    session: Session,
    buyer_id: int,
    order: Order,
    sellers: dict[int, SellerOrder],
    priced: PricedSelection,
) -> None:
    """Store the quoted breakdown and consume its vouchers in checkout's transaction."""
    price = priced.price
    for row in price.seller_orders:
        suborder = sellers[row.seller_id]
        if suborder.subtotal != row.subtotal:
            # Same transaction, same rows: a difference means the cart changed under us.
            raise QuoteError(
                "ERR_QUOTE_STALE",
                "Prices or vouchers changed. Review the updated total and try again.",
            )
        suborder.shop_discount = row.shop_discount
        suborder.platform_discount = row.platform_discount
        suborder.shipping_fee = row.shipping_fee
        suborder.shipping_discount = row.shipping_discount
        suborder.total_amount = row.total_amount
        suborder.pricing_policy_version = row.pricing_policy_version
    order.total_amount = price.grand_total

    applied = priced.applied
    usages = [
        (voucher, f"shop_vouchers.{seller_id}", sellers[seller_id].id, row.shop_discount)
        for seller_id, voucher in applied.shop.items()
        for row in price.seller_orders
        if row.seller_id == seller_id
    ]
    if applied.platform:
        usages.append((applied.platform, "platform_voucher", None, price.platform_discount))
    if applied.shipping:
        usages.append((applied.shipping, "shipping_voucher", None, price.shipping_discount))
    for voucher, field, seller_order_id, amount in usages:
        try:
            consume_voucher(
                session,
                voucher,
                buyer_id=buyer_id,
                order_id=order.id,
                seller_order_id=seller_order_id,
                discount_amount=amount,
            )
        except VoucherError as exc:
            raise QuoteError(exc.code, exc.message, exc.status_code, field=field) from exc


def checkout(
    session: Session, buyer_id: int, body: CheckoutInput, key: str
) -> tuple[OrderData, bool]:
    """Own the request session transaction; auth may already have begun it."""
    # Unset voucher fields are left out, so a legacy body keeps its original hash.
    fingerprint = hashlib.sha256(body.model_dump_json(exclude_unset=True).encode()).hexdigest()
    for attempt in range(5):
        try:
            existing = session.exec(select(Order).where(Order.request_key == key)).first()
            if existing:
                if existing.buyer_id != buyer_id or existing.request_hash != fingerprint:
                    raise CheckoutError(
                        "ERR_IDEMPOTENCY_CONFLICT", "Key was used for another request."
                    )
                return receipt(session, buyer_id, existing.id), False
            snapshot = resolve_delivery_snapshot(session, buyer_id, body)
            lines = session.exec(
                select(CartItem)
                .where(CartItem.buyer_id == buyer_id, CartItem.is_selected.is_(True))
                .order_by(CartItem.product_id)
            ).all()
            if not lines:
                session.rollback()
                existing = session.exec(select(Order).where(Order.request_key == key)).first()
                if existing is not None:
                    if existing.buyer_id != buyer_id or existing.request_hash != fingerprint:
                        raise CheckoutError(
                            "ERR_IDEMPOTENCY_CONFLICT", "Key was used for another request."
                        )
                    return receipt(session, buyer_id, existing.id), False
                has_cart = session.exec(
                    select(CartItem.id).where(CartItem.buyer_id == buyer_id)
                ).first()
                if has_cart is not None:
                    raise CheckoutError(
                        "ERR_EMPTY_CART", "Select at least one item for checkout.", 400
                    )
                raise CheckoutError("ERR_EMPTY_CART", "Your cart is empty.", 400)
            priced = None
            if body.quote_revision is not None:
                priced = price_selection(session, buyer_id, body)
                if priced.revision != body.quote_revision:
                    raise QuoteError(
                        "ERR_QUOTE_STALE",
                        "Prices or vouchers changed. Review the updated total and try again.",
                    )
                require_applied(priced)
            order = Order(
                buyer_id=buyer_id,
                total_amount=0,
                status="PENDING",
                request_key=key,
                request_hash=fingerprint,
                recipient_name=snapshot.recipient_name,
                phone_number=snapshot.phone_number,
                delivery_address=snapshot.delivery_address,
                # Older API clients did not send a method; retain their behavior
                # as COD while new checkout UI requests an explicit choice.
                payment_method=body.payment_method or "COD",
            )
            session.add(order)
            session.flush()
            sellers = {}
            for line in lines:
                product = session.get(Product, line.product_id)
                meta = session.exec(
                    select(ProductMetadata).where(ProductMetadata.product_id == line.product_id)
                ).first()
                is_mod = bool(meta and meta.is_moderated_deactivated)
                if product is None or not product.is_active or is_mod:
                    raise CheckoutError(
                        "ERR_PRODUCT_UNAVAILABLE",
                        f"Product {line.product_id} is no longer available.",
                    )
                variant = (
                    session.get(ProductVariant, line.variant_id)
                    if line.variant_id is not None
                    else None
                )
                if line.variant_id is not None and (
                    variant is None
                    or variant.product_id != product.id
                    or variant.seller_id != product.seller_id
                    or not variant.is_active
                ):
                    raise CheckoutError(
                        "ERR_PRODUCT_UNAVAILABLE",
                        f"Product variant {line.variant_id} is no longer available.",
                    )
                if (
                    variant is None
                    and session.exec(
                        select(ProductVariant.id).where(
                            ProductVariant.product_id == product.id,
                        )
                    ).first()
                    is not None
                ):
                    raise CheckoutError(
                        "ERR_PRODUCT_UNAVAILABLE",
                        f"Choose an active variant for product {product.name}.",
                    )
                if product.seller_id == buyer_id:
                    raise CheckoutError(
                        "ERR_SELF_PURCHASE",
                        "Sellers cannot purchase their own products.",
                        status=400,
                    )
                inventory = variant or product
                inventory_model = ProductVariant if variant is not None else Product
                reserve_filters = [
                    inventory_model.id == inventory.id,
                    inventory_model.version == inventory.version,
                    inventory_model.is_active.is_(True),
                    inventory_model.stock_quantity - inventory_model.reserved_stock
                    >= line.quantity,
                ]
                changed = session.exec(
                    update(inventory_model)
                    .where(*reserve_filters)
                    .values(
                        stock_quantity=inventory_model.stock_quantity - line.quantity,
                        version=inventory_model.version + 1,
                    )
                    .execution_options(synchronize_session=False)
                )
                if changed.rowcount != 1:
                    raise CheckoutError(
                        "ERR_STOCK_EXCEEDED",
                        f"Item {product.name} has insufficient stock or changed.",
                    )
                if product.seller_id not in sellers:
                    suborder = SellerOrder(
                        order_id=order.id,
                        seller_id=product.seller_id,
                        status="PENDING",
                        subtotal=0,
                        shop_discount=0,
                        platform_discount=0,
                        shipping_fee=0,
                        shipping_discount=0,
                        total_amount=0,
                        pricing_policy_version="LEGACY",
                    )
                    session.add(suborder)
                    session.flush()
                    sellers[product.seller_id] = suborder
                    create_notification(
                        session,
                        recipient_user_id=product.seller_id,
                        order_id=order.id,
                        event_key=f"order:{order.id}:created:seller:{product.seller_id}",
                        message=f"New order #{order.id} is waiting for processing.",
                        target_path="/seller/orders",
                    )
                suborder = sellers[product.seller_id]
                line_total = inventory.price * line.quantity
                suborder.subtotal += line_total
                suborder.total_amount += line_total
                session.add(
                    OrderItem(
                        seller_order_id=suborder.id,
                        product_id=product.id,
                        variant_id=variant.id if variant else None,
                        quantity=line.quantity,
                        unit_price=inventory.price,
                        product_name_snapshot=product.name,
                        variant_name_snapshot=variant.name if variant else None,
                        product_image_snapshot=(
                            variant.image_url or product.image_url if variant else product.image_url
                        ),
                        snapshot_initialized=True,
                    )
                )
                # Atomic sales_count increment avoiding ORM read-modify-write lost updates
                updated = session.exec(
                    update(ProductMetadata)
                    .where(ProductMetadata.product_id == product.id)
                    .values(sales_count=ProductMetadata.sales_count + line.quantity)
                    .execution_options(synchronize_session=False)
                )
                if updated.rowcount == 0:
                    session.exec(
                        sqlite_insert(ProductMetadata)
                        .values(
                            product_id=product.id,
                            category_id=None,
                            rating=0.0,
                            review_count=0,
                            sales_count=line.quantity,
                            created_at=datetime.now(UTC),
                        )
                        .on_conflict_do_update(
                            index_elements=["product_id"],
                            set_={"sales_count": ProductMetadata.sales_count + line.quantity},
                        )
                    )
                order.total_amount += inventory.price * line.quantity
                removed = session.exec(
                    delete(CartItem)
                    .where(
                        CartItem.id == line.id,
                        CartItem.buyer_id == buyer_id,
                        CartItem.product_id == line.product_id,
                        # IDs are reused, so the row must still hold the variant just ordered.
                        CartItem.variant_id == line.variant_id
                        if line.variant_id is not None
                        else CartItem.variant_id.is_(None),
                        CartItem.quantity == line.quantity,
                        CartItem.is_selected.is_(True),
                    )
                    .execution_options(synchronize_session=False)
                )
                if removed.rowcount != 1:
                    raise CheckoutError("ERR_CONCURRENCY_CONFLICT", "Cart changed. Please retry.")
            if priced is not None:
                apply_quoted_price(session, buyer_id, order, sellers, priced)
            for suborder in sellers.values():
                session.add(suborder)
            session.add(order)
            session.flush()
            result = receipt(session, buyer_id, order.id)
            session.commit()
            return result, True
        except (IntegrityError, OperationalError) as exc:
            session.rollback()
            busy = (getattr(exc.orig, "sqlite_errorcode", 0) or 0) & 255 in (5, 6)
            if isinstance(exc, IntegrityError):
                # Only a committed request-key collision is an idempotency race.
                # Other constraint failures must retain the database-failure response.
                collision = session.exec(select(Order).where(Order.request_key == key)).first()
                if collision is None:
                    raise
            elif not busy:
                raise
            if attempt == 4:
                raise CheckoutError(
                    "ERR_CONCURRENCY_CONFLICT", "Checkout changed. Please retry."
                ) from exc
            time.sleep(0.01 * (attempt + 1))
        except Exception:
            session.rollback()
            raise
    raise AssertionError("unreachable")
