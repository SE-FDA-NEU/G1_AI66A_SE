"""Tests for CartService on a real SQLite database (US03, #79).

Each test gets its own database file, and every service call runs in its own session, the way
one API request will. Results are checked by reading the rows back through a new session.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

import src.models  # noqa: F401  (registers every table on SQLModel.metadata)
import src.services.cart as cart_module
from src.models.cart_item import CartItem
from src.models.product import Product
from src.models.user import User
from src.schemas.cart import (
    AddCartItemRequest,
    CartLine,
    CartLineAvailability,
    UpdateCartItemRequest,
)
from src.services.cart import CartError, CartErrorCode, CartService

SELLER_ID = 1
BUYER_ID = 2
OTHER_BUYER_ID = 3

INVALID_QUANTITIES = [0, -1, 1.5, True, "2", None]


def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """A fresh database file with one seller and two buyers."""
    engine = create_engine(f"sqlite:///{tmp_path / 'cart.db'}")
    event.listen(engine, "connect", enable_foreign_keys)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                User(id=SELLER_ID, name="Seller", email="seller@test.local", role="seller"),
                User(id=BUYER_ID, name="Buyer", email="buyer@test.local", role="buyer"),
                User(id=OTHER_BUYER_ID, name="Other", email="other@test.local", role="buyer"),
            ]
        )
        session.commit()
    yield engine
    engine.dispose()


@contextmanager
def open_cart(engine: Engine) -> Iterator[CartService]:
    """A service on its own session, closed afterwards like at the end of a request."""
    with Session(engine) as session:
        yield CartService(session)


def add_product(
    engine: Engine,
    code: str,
    *,
    price: int = 100_000,
    stock: int = 10,
    reserved: int = 0,
    active: bool = True,
) -> int:
    with Session(engine) as session:
        product = Product(
            code=code,
            seller_id=SELLER_ID,
            name=f"Product {code}",
            price=price,
            stock_quantity=stock,
            reserved_stock=reserved,
            image_url=f"/images/{code.lower()}.jpg",
            is_active=active,
        )
        session.add(product)
        session.commit()
        return product.id


def change_product(engine: Engine, code: str, **changes: object) -> None:
    """Change a product outside the cart, as a seller or a checkout would."""
    with Session(engine) as session:
        product = session.exec(select(Product).where(Product.code == code)).one()
        for field, value in changes.items():
            setattr(product, field, value)
        session.add(product)
        session.commit()


def stored_lines(engine: Engine, buyer_id: int) -> list[tuple[str, int]]:
    """The buyer's cart lines as committed in the database."""
    with Session(engine) as session:
        rows = session.exec(
            select(Product.code, CartItem.quantity)
            .join(Product, Product.id == CartItem.product_id)
            .where(CartItem.buyer_id == buyer_id)
            .order_by(CartItem.id)
        ).all()
    return [(code, quantity) for code, quantity in rows]


def stored_stock(engine: Engine, code: str) -> tuple[int, int]:
    with Session(engine) as session:
        product = session.exec(select(Product).where(Product.code == code)).one()
        return product.stock_quantity, product.reserved_stock


def line_summary(lines: list[CartLine]) -> list[tuple[str, int, int]]:
    return [(line.product_code, line.quantity, line.line_total) for line in lines]


def test_buyer_without_lines_gets_an_empty_cart(engine: Engine) -> None:
    with open_cart(engine) as cart:
        snapshot = cart.get_cart(BUYER_ID)

    assert snapshot.items == []
    assert snapshot.cart_total == 0


def test_first_add_stores_one_line(engine: Engine) -> None:
    product_id = add_product(engine, "P-100", price=150_000)

    with open_cart(engine) as cart:
        result = cart.add_item(BUYER_ID, "P-100", 2)

    assert result.created is True
    assert result.cart.items == [
        CartLine(
            product_id=product_id,
            product_code="P-100",
            name="Product P-100",
            image_url="/images/p-100.jpg",
            unit_price=150_000,
            quantity=2,
            line_total=300_000,
            available_stock=10,
            availability=CartLineAvailability.AVAILABLE,
        )
    ]
    assert result.cart.cart_total == 300_000
    assert stored_lines(engine, BUYER_ID) == [("P-100", 2)]


def test_adding_the_same_product_again_increases_the_existing_line(engine: Engine) -> None:
    add_product(engine, "P-100")

    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)
    with open_cart(engine) as cart:
        result = cart.add_item(BUYER_ID, "P-100", 3)

    assert result.created is False
    assert line_summary(result.cart.items) == [("P-100", 5, 500_000)]
    assert stored_lines(engine, BUYER_ID) == [("P-100", 5)]


def test_quantity_change_survives_a_reload_with_recalculated_total(engine: Engine) -> None:
    add_product(engine, "P-100", price=100_000)
    add_product(engine, "P-101", price=50_000)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)
        cart.add_item(BUYER_ID, "P-101", 1)

    with open_cart(engine) as cart:
        updated = cart.update_item(BUYER_ID, "P-100", 3)
    with open_cart(engine) as cart:
        reloaded = cart.get_cart(BUYER_ID)

    assert updated == reloaded
    assert line_summary(reloaded.items) == [("P-100", 3, 300_000), ("P-101", 1, 50_000)]
    assert reloaded.cart_total == 350_000


def test_update_above_available_stock_keeps_the_previous_quantity(engine: Engine) -> None:
    add_product(engine, "P-100", price=100_000, stock=4)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)

    with open_cart(engine) as cart, pytest.raises(CartError) as error:
        cart.update_item(BUYER_ID, "P-100", 5)

    assert error.value.code is CartErrorCode.STOCK_EXCEEDED
    assert error.value.message == "Cannot add more than 4 items (available stock limit)"
    with open_cart(engine) as cart:
        snapshot = cart.get_cart(BUYER_ID)
    assert line_summary(snapshot.items) == [("P-100", 2, 200_000)]
    assert snapshot.cart_total == 200_000


def test_reserved_stock_is_not_available_to_the_cart(engine: Engine) -> None:
    add_product(engine, "P-100", stock=10, reserved=3)

    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 7)
        with pytest.raises(CartError) as error:
            cart.update_item(BUYER_ID, "P-100", 8)

    assert error.value.code is CartErrorCode.STOCK_EXCEEDED
    assert error.value.message == "Cannot add more than 7 items (available stock limit)"
    assert stored_lines(engine, BUYER_ID) == [("P-100", 7)]


def test_add_checks_stock_against_the_quantity_after_adding(engine: Engine) -> None:
    add_product(engine, "P-100", stock=10, reserved=3)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 5)

    with open_cart(engine) as cart, pytest.raises(CartError) as error:
        cart.add_item(BUYER_ID, "P-100", 3)

    assert error.value.code is CartErrorCode.STOCK_EXCEEDED
    assert stored_lines(engine, BUYER_ID) == [("P-100", 5)]


@pytest.mark.parametrize("quantity", INVALID_QUANTITIES)
def test_add_refuses_an_invalid_quantity(engine: Engine, quantity: object) -> None:
    add_product(engine, "P-100")

    with open_cart(engine) as cart, pytest.raises(CartError) as error:
        cart.add_item(BUYER_ID, "P-100", quantity)

    assert error.value.code is CartErrorCode.INVALID_QUANTITY
    assert stored_lines(engine, BUYER_ID) == []


@pytest.mark.parametrize("quantity", INVALID_QUANTITIES)
def test_update_refuses_an_invalid_quantity(engine: Engine, quantity: object) -> None:
    add_product(engine, "P-100")
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)

    with open_cart(engine) as cart, pytest.raises(CartError) as error:
        cart.update_item(BUYER_ID, "P-100", quantity)

    assert error.value.code is CartErrorCode.INVALID_QUANTITY
    assert stored_lines(engine, BUYER_ID) == [("P-100", 2)]


@pytest.mark.parametrize("quantity", [True, 1.5, 2.0, "2", None])
def test_request_schemas_refuse_a_non_integer_quantity(quantity: object) -> None:
    """Wrong types stop at the HTTP layer (422) before the service runs."""
    with pytest.raises(ValidationError):
        AddCartItemRequest(product_code="P-100", quantity=quantity)
    with pytest.raises(ValidationError):
        UpdateCartItemRequest(quantity=quantity)


@pytest.mark.parametrize("quantity", [0, -1])
def test_request_schemas_leave_non_positive_quantity_to_the_service(quantity: int) -> None:
    """Zero and negatives pass the schema so the service answers ERR_INVALID_QUANTITY (400)."""
    assert AddCartItemRequest(product_code="P-100", quantity=quantity).quantity == quantity
    assert UpdateCartItemRequest(quantity=quantity).quantity == quantity


def test_unknown_product_code_is_refused(engine: Engine) -> None:
    with open_cart(engine) as cart, pytest.raises(CartError) as error:
        cart.add_item(BUYER_ID, "P-999", 1)

    assert error.value.code is CartErrorCode.PRODUCT_NOT_FOUND


def test_withdrawn_product_is_flagged_and_cannot_be_added_or_updated(engine: Engine) -> None:
    add_product(engine, "P-100")
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 1)
    change_product(engine, "P-100", is_active=False)

    with open_cart(engine) as cart:
        with pytest.raises(CartError) as add_error:
            cart.add_item(BUYER_ID, "P-100", 1)
        with pytest.raises(CartError) as update_error:
            cart.update_item(BUYER_ID, "P-100", 2)
        snapshot = cart.get_cart(BUYER_ID)

    assert add_error.value.code is CartErrorCode.PRODUCT_UNAVAILABLE
    assert update_error.value.code is CartErrorCode.PRODUCT_UNAVAILABLE
    assert snapshot.items[0].availability is CartLineAvailability.UNAVAILABLE
    assert stored_lines(engine, BUYER_ID) == [("P-100", 1)]

    with open_cart(engine) as cart:
        emptied = cart.remove_item(BUYER_ID, "P-100")
    assert emptied.items == []


def test_out_of_stock_product_cannot_be_added(engine: Engine) -> None:
    add_product(engine, "P-100", stock=3, reserved=3)

    with open_cart(engine) as cart, pytest.raises(CartError) as error:
        cart.add_item(BUYER_ID, "P-100", 1)

    assert error.value.code is CartErrorCode.STOCK_EXCEEDED
    assert error.value.message == "This product is out of stock."
    assert stored_lines(engine, BUYER_ID) == []


def test_stock_drop_flags_the_line_without_changing_it(engine: Engine) -> None:
    add_product(engine, "P-100", stock=10)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 5)
    change_product(engine, "P-100", stock_quantity=3)

    with open_cart(engine) as cart:
        line = cart.get_cart(BUYER_ID).items[0]

    assert (line.quantity, line.available_stock) == (5, 3)
    assert line.availability is CartLineAvailability.INSUFFICIENT_STOCK
    assert stored_lines(engine, BUYER_ID) == [("P-100", 5)]

    with open_cart(engine) as cart:
        reduced = cart.update_item(BUYER_ID, "P-100", 3)
    assert reduced.items[0].availability is CartLineAvailability.AVAILABLE


def test_update_or_remove_of_a_product_not_in_the_cart_is_refused(engine: Engine) -> None:
    add_product(engine, "P-100")

    with open_cart(engine) as cart:
        with pytest.raises(CartError) as update_error:
            cart.update_item(BUYER_ID, "P-100", 1)
        with pytest.raises(CartError) as remove_error:
            cart.remove_item(BUYER_ID, "P-999")

    assert update_error.value.code is CartErrorCode.CART_ITEM_NOT_FOUND
    assert remove_error.value.code is CartErrorCode.CART_ITEM_NOT_FOUND


def test_removing_a_line_keeps_the_others_and_recalculates_the_total(engine: Engine) -> None:
    add_product(engine, "P-100", price=100_000)
    add_product(engine, "P-101", price=50_000)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 1)
        cart.add_item(BUYER_ID, "P-101", 2)

    with open_cart(engine) as cart:
        snapshot = cart.remove_item(BUYER_ID, "P-100")

    assert line_summary(snapshot.items) == [("P-101", 2, 100_000)]
    assert snapshot.cart_total == 100_000
    assert stored_lines(engine, BUYER_ID) == [("P-101", 2)]


def test_removing_the_last_line_empties_the_cart(engine: Engine) -> None:
    add_product(engine, "P-100")
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 1)

    with open_cart(engine) as cart:
        snapshot = cart.remove_item(BUYER_ID, "P-100")

    assert snapshot.items == []
    assert snapshot.cart_total == 0
    assert stored_lines(engine, BUYER_ID) == []


def test_buyers_have_independent_carts(engine: Engine) -> None:
    add_product(engine, "P-100")

    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)
        cart.add_item(OTHER_BUYER_ID, "P-100", 5)
        cart.update_item(OTHER_BUYER_ID, "P-100", 1)

    assert stored_lines(engine, BUYER_ID) == [("P-100", 2)]
    assert stored_lines(engine, OTHER_BUYER_ID) == [("P-100", 1)]

    with open_cart(engine) as cart:
        cart.remove_item(OTHER_BUYER_ID, "P-100")
        assert line_summary(cart.get_cart(BUYER_ID).items) == [("P-100", 2, 200_000)]


def test_a_buyer_cannot_change_another_buyers_line(engine: Engine) -> None:
    add_product(engine, "P-100")
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)

    with open_cart(engine) as cart:
        with pytest.raises(CartError) as update_error:
            cart.update_item(OTHER_BUYER_ID, "P-100", 3)
        with pytest.raises(CartError) as remove_error:
            cart.remove_item(OTHER_BUYER_ID, "P-100")
        other_cart = cart.get_cart(OTHER_BUYER_ID)

    assert update_error.value.code is CartErrorCode.CART_ITEM_NOT_FOUND
    assert remove_error.value.code is CartErrorCode.CART_ITEM_NOT_FOUND
    assert other_cart.items == []
    assert stored_lines(engine, BUYER_ID) == [("P-100", 2)]


def test_cart_changes_never_touch_product_stock(engine: Engine) -> None:
    add_product(engine, "P-100", stock=10, reserved=3)

    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)
    assert stored_stock(engine, "P-100") == (10, 3)

    with open_cart(engine) as cart:
        cart.update_item(BUYER_ID, "P-100", 4)
    assert stored_stock(engine, "P-100") == (10, 3)

    with open_cart(engine) as cart:
        cart.remove_item(BUYER_ID, "P-100")
    assert stored_stock(engine, "P-100") == (10, 3)


def test_cart_is_priced_from_the_current_database_price(engine: Engine) -> None:
    add_product(engine, "P-100", price=100_000)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)
    change_product(engine, "P-100", price=120_000)

    with open_cart(engine) as cart:
        snapshot = cart.get_cart(BUYER_ID)

    assert snapshot.items[0].unit_price == 120_000
    assert line_summary(snapshot.items) == [("P-100", 2, 240_000)]
    assert snapshot.cart_total == 240_000


def test_concurrent_insert_of_the_same_line_is_a_controlled_conflict(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another request inserted the line after this one looked for it."""
    add_product(engine, "P-100")
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)
    monkeypatch.setattr(cart_module, "find_cart_item_for_product", lambda *_args: None)

    with open_cart(engine) as cart:
        with pytest.raises(CartError) as error:
            cart.add_item(BUYER_ID, "P-100", 1)
        after_rollback = cart.get_cart(BUYER_ID)

    assert error.value.code is CartErrorCode.CONCURRENCY_CONFLICT
    assert line_summary(after_rollback.items) == [("P-100", 2, 200_000)]
    assert stored_lines(engine, BUYER_ID) == [("P-100", 2)]
