"""Shopping cart business rules (US03, BR2) on top of the `cart_items` and `products` tables.

The caller passes a database session and the authenticated buyer id; this module never reads
tokens or HTTP requests. Each mutation commits or rolls back on its own, so a router must not
commit again.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, select

from src.models.cart_item import CartItem
from src.models.product import Product
from src.schemas.cart import Cart, CartLine, CartLineAvailability

INVALID_QUANTITY_MESSAGE = "Quantity must be a whole number of at least 1."
PRODUCT_NOT_FOUND_MESSAGE = "This product does not exist."
PRODUCT_UNAVAILABLE_MESSAGE = "This product is no longer available."
OUT_OF_STOCK_MESSAGE = "This product is out of stock."
CART_ITEM_NOT_FOUND_MESSAGE = "This product is not in your cart."
CONCURRENCY_CONFLICT_MESSAGE = (
    "Your cart was changed by another request. Please reload and try again."
)

MAX_MUTATION_ATTEMPTS = 5
RETRY_BACKOFF_SECONDS = 0.01
SQLITE_BUSY = 5
SQLITE_LOCKED = 6

T = TypeVar("T")


class CartErrorCode(StrEnum):
    """Stable error codes from the API contract; the router maps each one to an HTTP status."""

    INVALID_QUANTITY = "ERR_INVALID_QUANTITY"
    PRODUCT_NOT_FOUND = "ERR_PRODUCT_NOT_FOUND"
    PRODUCT_UNAVAILABLE = "ERR_PRODUCT_UNAVAILABLE"
    STOCK_EXCEEDED = "ERR_STOCK_EXCEEDED"
    CART_ITEM_NOT_FOUND = "ERR_CART_ITEM_NOT_FOUND"
    CONCURRENCY_CONFLICT = "ERR_CONCURRENCY_CONFLICT"
    SELF_PURCHASE = "ERR_SELF_PURCHASE"


class CartError(Exception):
    """A cart request that breaks a business rule; the cart is left unchanged."""

    def __init__(self, code: CartErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StaleCartLine(Exception):
    """A line changed between being read and being increased; the change must run again."""


@dataclass(frozen=True)
class AddItemResult:
    """The cart after an add; `created` tells a new line (201) from an increased one (200)."""

    cart: Cart
    created: bool


def validate_quantity(quantity: object) -> None:
    """Accept only positive integers; booleans, fractions and numeric strings are refused."""
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise CartError(CartErrorCode.INVALID_QUANTITY, INVALID_QUANTITY_MESSAGE)


def get_available_stock(product: Product) -> int:
    """Stock a buyer may still put in a cart: physical stock minus stock reserved by orders."""
    return product.stock_quantity - product.reserved_stock


def get_line_availability(product: Product, quantity: int) -> CartLineAvailability:
    """Classify `quantity` of `product` against its current availability."""
    if not product.is_active:
        return CartLineAvailability.UNAVAILABLE
    if quantity > get_available_stock(product):
        return CartLineAvailability.INSUFFICIENT_STOCK
    return CartLineAvailability.AVAILABLE


def validate_purchasable_quantity(product: Product, quantity: int) -> None:
    """Refuse a cart quantity the product cannot satisfy right now (BR2)."""
    availability = get_line_availability(product, quantity)
    if availability is CartLineAvailability.UNAVAILABLE:
        raise CartError(CartErrorCode.PRODUCT_UNAVAILABLE, PRODUCT_UNAVAILABLE_MESSAGE)
    if availability is CartLineAvailability.INSUFFICIENT_STOCK:
        available_stock = get_available_stock(product)
        message = (
            OUT_OF_STOCK_MESSAGE
            if available_stock == 0
            else f"Cannot add more than {available_stock} items (available stock limit)"
        )
        raise CartError(CartErrorCode.STOCK_EXCEEDED, message)


def find_product(session: Session, product_code: str) -> Product:
    """Resolve a public product code such as `P-100`."""
    product = session.exec(select(Product).where(Product.code == product_code)).first()
    if product is None:
        raise CartError(CartErrorCode.PRODUCT_NOT_FOUND, PRODUCT_NOT_FOUND_MESSAGE)
    return product


def find_cart_item_for_product(
    session: Session, buyer_id: int, product_id: int
) -> CartItem | None:
    """Return the buyer's line for a product, or None when the product is not in the cart."""
    return session.exec(
        select(CartItem).where(CartItem.buyer_id == buyer_id, CartItem.product_id == product_id)
    ).first()


def find_buyer_cart_item(
    session: Session, buyer_id: int, product_code: str
) -> tuple[CartItem, Product]:
    """Return the buyer's line for a product code; lines of other buyers are never matched."""
    row = session.exec(
        select(CartItem, Product)
        .join(Product, Product.id == CartItem.product_id)
        .where(CartItem.buyer_id == buyer_id, Product.code == product_code)
    ).first()
    if row is None:
        raise CartError(CartErrorCode.CART_ITEM_NOT_FOUND, CART_ITEM_NOT_FOUND_MESSAGE)
    cart_item, product = row
    return cart_item, product


def increase_line(
    session: Session, cart_item: CartItem, quantity: int, available_stock: int
) -> None:
    """Add to a line in one UPDATE, so requests adding at the same time never overwrite each other.

    The stock limit is part of the WHERE clause: when another request filled the line in
    between, no row changes and StaleCartLine makes the change run again on fresh data.
    """
    result = session.exec(
        update(CartItem)
        .where(CartItem.id == cart_item.id, CartItem.quantity + quantity <= available_stock)
        .values(quantity=CartItem.quantity + quantity)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        raise StaleCartLine
    session.expire(cart_item)


def is_lost_race(error: Exception) -> bool:
    """Whether a change failed only because another request changed the same cart first."""
    if isinstance(error, (IntegrityError, StaleCartLine)):
        return True
    if not isinstance(error, OperationalError):
        return False
    # SQLite refuses a write with BUSY or LOCKED while, or after, another request writes.
    code = getattr(error.orig, "sqlite_errorcode", None)
    return code is not None and code & 0xFF in (SQLITE_BUSY, SQLITE_LOCKED)


def to_cart_line(cart_item: CartItem, product: Product) -> CartLine:
    """Price one line from the current product row."""
    return CartLine(
        product_id=product.id,
        product_code=product.code,
        name=product.name,
        image_url=product.image_url,
        unit_price=product.price,
        quantity=cart_item.quantity,
        line_total=product.price * cart_item.quantity,
        available_stock=get_available_stock(product),
        availability=get_line_availability(product, cart_item.quantity),
    )


def build_cart_snapshot(session: Session, buyer_id: int) -> Cart:
    """Read the buyer's cart with current prices and stock, in the order lines were added.

    Lines whose stock dropped or whose product was withdrawn are kept and flagged through
    `availability`; they are never removed or shrunk silently.
    """
    rows = session.exec(
        select(CartItem, Product)
        .join(Product, Product.id == CartItem.product_id)
        .where(CartItem.buyer_id == buyer_id)
        .order_by(CartItem.id)
    ).all()
    lines = [to_cart_line(cart_item, product) for cart_item, product in rows]
    return Cart(items=lines, cart_total=sum(line.line_total for line in lines))


class CartService:
    """Read and change one buyer's cart. Product stock is only read, never changed."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_cart(self, buyer_id: int) -> Cart:
        """Return the cart; a buyer without lines gets an empty cart with total 0."""
        return build_cart_snapshot(self.session, buyer_id)

    def add_item(self, buyer_id: int, product_code: str, quantity: int) -> AddItemResult:
        """Add a new line, or increase the existing one; the resulting quantity must fit stock."""
        validate_quantity(quantity)

        def change() -> AddItemResult:
            product = find_product(self.session, product_code)
            if product.seller_id == buyer_id:
                raise CartError(
                    CartErrorCode.SELF_PURCHASE,
                    "You cannot add your own product to your cart.",
                )
            cart_item = find_cart_item_for_product(self.session, buyer_id, product.id)
            if cart_item is None:
                validate_purchasable_quantity(product, quantity)
                self.session.add(
                    CartItem(buyer_id=buyer_id, product_id=product.id, quantity=quantity)
                )
                return AddItemResult(cart=self._flush_and_snapshot(buyer_id), created=True)
            validate_purchasable_quantity(product, cart_item.quantity + quantity)
            increase_line(self.session, cart_item, quantity, get_available_stock(product))
            return AddItemResult(cart=self._flush_and_snapshot(buyer_id), created=False)

        return self._run_mutation(change)

    def update_item(self, buyer_id: int, product_code: str, quantity: int) -> Cart:
        """Replace a line's quantity. Zero is refused: the buyer removes the line instead."""
        validate_quantity(quantity)

        def change() -> Cart:
            cart_item, product = find_buyer_cart_item(self.session, buyer_id, product_code)
            validate_purchasable_quantity(product, quantity)
            cart_item.quantity = quantity
            self.session.add(cart_item)
            return self._flush_and_snapshot(buyer_id)

        return self._run_mutation(change)

    def remove_item(self, buyer_id: int, product_code: str) -> Cart:
        """Delete one line of the buyer's cart, including a line whose product was withdrawn."""

        def change() -> Cart:
            cart_item, _product = find_buyer_cart_item(self.session, buyer_id, product_code)
            self.session.delete(cart_item)
            return self._flush_and_snapshot(buyer_id)

        return self._run_mutation(change)

    def _flush_and_snapshot(self, buyer_id: int) -> Cart:
        self.session.flush()
        return build_cart_snapshot(self.session, buyer_id)

    def _run_mutation(self, change: Callable[[], T]) -> T:
        """Run `change` and commit it, or roll all of it back.

        When another request wins a race on the same cart (both insert the same line, a line
        changes under an increase, or SQLite is busy), the change runs again on fresh data, at
        most MAX_MUTATION_ATTEMPTS times. After that the buyer gets ERR_CONCURRENCY_CONFLICT
        instead of a 500.
        """
        attempt = 1
        while True:
            try:
                result = change()
                self.session.commit()
                return result
            except Exception as exc:
                self.session.rollback()
                if not is_lost_race(exc):
                    raise
                if attempt == MAX_MUTATION_ATTEMPTS:
                    raise CartError(
                        CartErrorCode.CONCURRENCY_CONFLICT, CONCURRENCY_CONFLICT_MESSAGE
                    ) from exc
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                attempt += 1
