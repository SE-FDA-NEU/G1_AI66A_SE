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
from src.schemas.orders import (
    CheckoutInput,
    CheckoutRequest,
    DeliverySnapshot,
    OrderData,
    OrderLine,
    SubOrderSummary,
)
from src.services.addresses import AddressError, owned_address
from src.services.notifications import create_notification


class CheckoutError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


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
    rows = session.exec(
        select(OrderItem, Product)
        .join(SellerOrder, SellerOrder.id == OrderItem.seller_order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(SellerOrder.order_id == order.id)
        .order_by(OrderItem.id)
    ).all()
    values = order.model_dump(exclude={"buyer_id", "request_key", "request_hash"})
    values["created_at"] = order.created_at.replace(tzinfo=UTC)
    if order.shipped_at:
        values["shipped_at"] = order.shipped_at.replace(tzinfo=UTC)
    if order.delivered_at:
        values["delivered_at"] = order.delivered_at.replace(tzinfo=UTC)
    if order.completed_at:
        values["completed_at"] = order.completed_at.replace(tzinfo=UTC)
    sub_orders = session.exec(
        select(SellerOrder).where(SellerOrder.order_id == order.id).order_by(SellerOrder.id)
    ).all()
    sub_order_map = {so.id: so for so in sub_orders}
    visible_sub_orders = sub_orders
    if seller_id is not None:
        visible_sub_orders = [so for so in sub_orders if so.seller_id == seller_id]

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
                shipped_at=so.shipped_at.replace(tzinfo=UTC) if so.shipped_at else None,
                delivered_at=so.delivered_at.replace(tzinfo=UTC) if so.delivered_at else None,
                completed_at=so.completed_at.replace(tzinfo=UTC) if so.completed_at else None,
            )
            for so in visible_sub_orders
            if so.id is not None
        ],
    )


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


def checkout(
    session: Session, buyer_id: int, body: CheckoutInput, key: str
) -> tuple[OrderData, bool]:
    """Own the request session transaction; auth may already have begun it."""
    fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
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
            order = Order(
                buyer_id=buyer_id,
                total_amount=0,
                status="PENDING",
                request_key=key,
                request_hash=fingerprint,
                recipient_name=snapshot.recipient_name,
                phone_number=snapshot.phone_number,
                delivery_address=snapshot.delivery_address,
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
                        order_id=order.id, seller_id=product.seller_id, status="PENDING"
                    )
                    session.add(suborder)
                    session.flush()
                    sellers[product.seller_id] = suborder.id
                    create_notification(
                        session,
                        recipient_user_id=product.seller_id,
                        order_id=order.id,
                        event_key=f"order:{order.id}:created:seller:{product.seller_id}",
                        message=f"New order #{order.id} is waiting for processing.",
                        target_path="/seller/orders",
                    )
                session.add(
                    OrderItem(
                        seller_order_id=sellers[product.seller_id],
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
