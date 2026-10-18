"""Atomic checkout and buyer-owned receipts (US04)."""

import hashlib
import time
from datetime import UTC

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, select

from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.seller_order import SellerOrder
from src.schemas.orders import CheckoutRequest, OrderData, OrderLine


class CheckoutError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def receipt(session: Session, buyer_id: int, order_id: int) -> OrderData:
    order = session.exec(
        select(Order).where(Order.id == order_id, Order.buyer_id == buyer_id)
    ).first()
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
    return OrderData(
        **values,
        items=[
            OrderLine(
                **item.model_dump(),
                product_code=product.code,
                product_name=product.name,
                line_total=item.quantity * item.unit_price,
            )
            for item, product in rows
        ],
    )


def checkout(
    session: Session, buyer_id: int, body: CheckoutRequest, key: str
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
            lines = session.exec(
                select(CartItem).where(CartItem.buyer_id == buyer_id).order_by(CartItem.product_id)
            ).all()
            if not lines:
                raise CheckoutError("ERR_EMPTY_CART", "Your cart is empty.", 400)
            order = Order(
                buyer_id=buyer_id,
                total_amount=0,
                status="PENDING",
                request_key=key,
                request_hash=fingerprint,
                **body.model_dump(),
            )
            session.add(order)
            session.flush()
            sellers = {}
            for line in lines:
                product = session.get(Product, line.product_id)
                if product is None or not product.is_active:
                    raise CheckoutError(
                        "ERR_PRODUCT_UNAVAILABLE",
                        f"Product {line.product_id} is no longer available.",
                    )
                changed = session.exec(
                    update(Product)
                    .where(
                        Product.id == product.id,
                        Product.version == product.version,
                        Product.is_active.is_(True),
                        Product.stock_quantity - Product.reserved_stock >= line.quantity,
                    )
                    .values(
                        stock_quantity=Product.stock_quantity - line.quantity,
                        version=Product.version + 1,
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
                session.add(
                    OrderItem(
                        seller_order_id=sellers[product.seller_id],
                        product_id=product.id,
                        quantity=line.quantity,
                        unit_price=product.price,
                    )
                )
                order.total_amount += product.price * line.quantity
                removed = session.exec(
                    delete(CartItem)
                    .where(
                        CartItem.id == line.id,
                        CartItem.buyer_id == buyer_id,
                        CartItem.product_id == line.product_id,
                        CartItem.quantity == line.quantity,
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
