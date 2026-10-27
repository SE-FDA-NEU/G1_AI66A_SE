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
from src.models.product_variant import ProductVariant
from src.models.user import User
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


def get_available_stock(product: Product, variant: ProductVariant | None = None) -> int:
    """Stock a buyer may still put in a cart: physical stock minus stock reserved by orders."""
    item = variant or product
    return item.stock_quantity - item.reserved_stock


def get_line_availability(
    product: Product, quantity: int, variant: ProductVariant | None = None
) -> CartLineAvailability:
    """Classify `quantity` of `product` against its current availability."""
    if not product.is_active or (variant is not None and not variant.is_active):
        return CartLineAvailability.UNAVAILABLE
    if quantity > get_available_stock(product, variant):
        return CartLineAvailability.INSUFFICIENT_STOCK
    return CartLineAvailability.AVAILABLE


def validate_purchasable_quantity(
    product: Product, quantity: int, variant: ProductVariant | None = None
) -> None:
    """Refuse a cart quantity the product cannot satisfy right now (BR2)."""
    availability = get_line_availability(product, quantity, variant)
    if availability is CartLineAvailability.UNAVAILABLE:
        raise CartError(CartErrorCode.PRODUCT_UNAVAILABLE, PRODUCT_UNAVAILABLE_MESSAGE)
    if availability is CartLineAvailability.INSUFFICIENT_STOCK:
        available_stock = get_available_stock(product, variant)
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
    session: Session, buyer_id: int, product_id: int, variant_id: int | None = None
) -> CartItem | None:
    """Return the buyer's line for this product and selected variant."""
    variant_filter = (
        CartItem.variant_id == variant_id
        if variant_id is not None
        else CartItem.variant_id.is_(None)
    )
    return session.exec(
        select(CartItem).where(
            CartItem.buyer_id == buyer_id,
            CartItem.product_id == product_id,
            variant_filter,
        )
    ).first()


def find_buyer_cart_item(
    session: Session, buyer_id: int, product_code: str, variant_id: int | None
) -> tuple[CartItem, Product]:
    """Return the buyer's line for a product code; lines of other buyers are never matched."""
    row = session.exec(
        select(CartItem, Product)
        .join(Product, Product.id == CartItem.product_id)
        .where(
            CartItem.buyer_id == buyer_id,
            Product.code == product_code,
            CartItem.variant_id == variant_id
            if variant_id is not None
            else CartItem.variant_id.is_(None),
        )
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


def to_cart_line(
    cart_item: CartItem,
    product: Product,
    seller: User,
    variant: ProductVariant | None = None,
) -> CartLine:
    """Price one line from the current product row."""
    availability = get_line_availability(product, cart_item.quantity, variant)
    current_price = variant.price if variant is not None else product.price
    baseline = cart_item.price_at_add if cart_item.price_at_add is not None else current_price
    return CartLine(
        cart_item_id=cart_item.id,
        seller_id=seller.id,
        seller_name=seller.name,
        is_selected=cart_item.is_selected and availability == CartLineAvailability.AVAILABLE,
        price_at_add=baseline,
        price_changed=baseline != current_price,
        product_id=product.id,
        variant_id=variant.id if variant else None,
        variant_name=variant.name if variant else None,
        product_code=product.code,
        name=product.name,
        image_url=variant.image_url or product.image_url if variant else product.image_url,
        unit_price=current_price,
        quantity=cart_item.quantity,
        line_total=current_price * cart_item.quantity,
        available_stock=get_available_stock(product, variant),
        availability=availability,
    )


def update_line_fields(session: Session, line: CartItem, **values: object) -> None:
    """Do not update a replacement row if SQLite reused a removed line's ID."""
    changed = session.exec(
        update(CartItem)
        .where(
            CartItem.id == line.id,
            CartItem.buyer_id == line.buyer_id,
            CartItem.product_id == line.product_id,
            CartItem.quantity == line.quantity,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise StaleCartLine
    session.expire(line)


def build_cart_snapshot(session: Session, buyer_id: int) -> Cart:
    """Read the buyer's cart with current prices and stock, in the order lines were added.

    Lines whose stock dropped or whose product was withdrawn are kept and flagged through
    `availability`; they are never removed or shrunk silently.
    """
    rows = session.exec(
        select(CartItem, Product, User, ProductVariant)
        .join(Product, Product.id == CartItem.product_id)
        .join(User, User.id == Product.seller_id)
        .outerjoin(ProductVariant, ProductVariant.id == CartItem.variant_id)
        .where(CartItem.buyer_id == buyer_id)
        .order_by(CartItem.id)
    ).all()
    lines = []
    for cart_item, product, seller, variant in rows:
        changes = {}
        if cart_item.price_at_add is None:
            changes["price_at_add"] = variant.price if variant else product.price
        if cart_item.is_selected and (
            get_line_availability(product, cart_item.quantity, variant)
            != CartLineAvailability.AVAILABLE
        ):
            changes["is_selected"] = False
        if changes:
            update_line_fields(session, cart_item, **changes)
        line = to_cart_line(cart_item, product, seller, variant)
        lines.append(line)
    return Cart(
        items=lines,
        cart_total=sum(line.line_total for line in lines),
        selected_total=sum(line.line_total for line in lines if line.is_selected),
    )


class CartService:
    """Read and change one buyer's cart. Product stock is only read, never changed."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_cart(self, buyer_id: int) -> Cart:
        """Return current totals and persist deselection of rows that cannot be bought.

        Selection does not reserve stock. Once a row becomes unavailable it stays
        deselected even if the seller replenishes stock before the next cart visit.
        """
        return self._run_mutation(lambda: build_cart_snapshot(self.session, buyer_id))

    def add_item(
        self, buyer_id: int, product_code: str, quantity: int, variant_id: int | None = None
    ) -> AddItemResult:
        """Add a new line, or increase the existing one; the resulting quantity must fit stock."""
        validate_quantity(quantity)

        def change() -> AddItemResult:
            product = find_product(self.session, product_code)
            if product.seller_id == buyer_id:
                raise CartError(
                    CartErrorCode.SELF_PURCHASE,
                    "You cannot add your own product to your cart.",
                )
            variant = self.session.get(ProductVariant, variant_id) if variant_id else None
            if variant_id is not None and (
                variant is None or variant.product_id != product.id or not variant.is_active
            ):
                raise CartError(
                    CartErrorCode.PRODUCT_UNAVAILABLE,
                    "This product variant is no longer available.",
                )
            has_any_variant = self.session.exec(
                select(ProductVariant.id).where(
                    ProductVariant.product_id == product.id,
                )
            ).first()
            if variant is None and has_any_variant is not None:
                raise CartError(
                    CartErrorCode.PRODUCT_UNAVAILABLE,
                    "Choose an available product variant before adding it to your cart.",
                )
            cart_item = (
                find_cart_item_for_product(self.session, buyer_id, product.id)
                if variant_id is None
                else find_cart_item_for_product(self.session, buyer_id, product.id, variant_id)
            )
            if cart_item is None:
                validate_purchasable_quantity(product, quantity, variant)
                self.session.add(
                    CartItem(
                        buyer_id=buyer_id,
                        product_id=product.id,
                        variant_id=variant_id,
                        quantity=quantity,
                        price_at_add=variant.price if variant else product.price,
                        is_selected=True,
                    )
                )
                return AddItemResult(cart=self._flush_and_snapshot(buyer_id), created=True)
            validate_purchasable_quantity(product, cart_item.quantity + quantity, variant)
            increase_line(
                self.session,
                cart_item,
                quantity,
                get_available_stock(product, variant),
            )
            return AddItemResult(cart=self._flush_and_snapshot(buyer_id), created=False)

        return self._run_mutation(change)

    def update_item(
        self, buyer_id: int, product_code: str, quantity: int, variant_id: int | None = None
    ) -> Cart:
        """Replace a line's quantity. Zero is refused: the buyer removes the line instead."""
        validate_quantity(quantity)

        def change() -> Cart:
            cart_item, product = find_buyer_cart_item(
                self.session, buyer_id, product_code, variant_id
            )
            variant = self.session.get(ProductVariant, variant_id) if variant_id else None
            validate_purchasable_quantity(product, quantity, variant)
            cart_item.quantity = quantity
            self.session.add(cart_item)
            return self._flush_and_snapshot(buyer_id)

        return self._run_mutation(change)

    def remove_item(self, buyer_id: int, product_code: str, variant_id: int | None = None) -> Cart:
        """Delete one line of the buyer's cart, including a line whose product was withdrawn."""

        def change() -> Cart:
            cart_item, _product = find_buyer_cart_item(
                self.session, buyer_id, product_code, variant_id
            )
            self.session.delete(cart_item)
            return self._flush_and_snapshot(buyer_id)

        return self._run_mutation(change)

    def select_item(self, buyer_id: int, item_id: int, selected: bool) -> Cart:
        """Change one owned row; selecting an unavailable quantity is refused."""

        def change() -> Cart:
            row = self.session.exec(
                select(CartItem, Product, ProductVariant)
                .join(Product, Product.id == CartItem.product_id)
                .outerjoin(ProductVariant, ProductVariant.id == CartItem.variant_id)
                .where(CartItem.id == item_id, CartItem.buyer_id == buyer_id)
            ).first()
            if row is None:
                raise CartError(CartErrorCode.CART_ITEM_NOT_FOUND, CART_ITEM_NOT_FOUND_MESSAGE)
            line, product, variant = row
            if selected:
                validate_purchasable_quantity(product, line.quantity, variant)
            update_line_fields(self.session, line, is_selected=selected)
            return self._flush_and_snapshot(buyer_id)

        return self._run_mutation(change)

    def select_shop(self, buyer_id: int, seller_id: int, selected: bool) -> Cart:
        """Change a shop atomically, keeping its unavailable rows deselected."""

        def change() -> Cart:
            rows = self.session.exec(
                select(CartItem, Product, ProductVariant)
                .join(Product, Product.id == CartItem.product_id)
                .outerjoin(ProductVariant, ProductVariant.id == CartItem.variant_id)
                .where(CartItem.buyer_id == buyer_id, Product.seller_id == seller_id)
            ).all()
            if not rows:
                raise CartError(CartErrorCode.CART_ITEM_NOT_FOUND, CART_ITEM_NOT_FOUND_MESSAGE)
            for line, product, variant in rows:
                available = (
                    get_line_availability(product, line.quantity, variant)
                    == CartLineAvailability.AVAILABLE
                )
                update_line_fields(self.session, line, is_selected=selected and available)
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
