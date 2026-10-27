"""Tests for CartService on a real SQLite database (US03, #79).

Every service call runs in its own session, the way one API request does.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlmodel import Session

import src.services.cart as cart_module
from src.models.cart_item import CartItem
from src.schemas.cart import (
    AddCartItemRequest,
    CartLine,
    CartLineAvailability,
    UpdateCartItemRequest,
)
from src.services.cart import CartError, CartErrorCode, CartService, is_lost_race
from tests.cart_db import (
    BUYER_ID,
    OTHER_BUYER_ID,
    add_product,
    change_product,
    create_cart_engine,
    stored_lines,
    stored_stock,
)

INVALID_QUANTITIES = [0, -1, 1.5, True, "2", None]


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_cart_engine(tmp_path / "cart.db")
    yield engine
    engine.dispose()


@contextmanager
def open_cart(engine: Engine) -> Iterator[CartService]:
    """A service on its own session, closed afterwards like at the end of a request."""
    with Session(engine) as session:
        yield CartService(session)


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
            cart_item_id=1,
            seller_id=1,
            seller_name="Seller",
            is_selected=True,
            price_at_add=150_000,
            price_changed=False,
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


# (stock_quantity, reserved_stock) whose available stock is 10, 7 and 1.
STOCK_LEVELS = [(10, 0), (10, 3), (1, 0)]

# One more than the available stock, including products with nothing left to sell.
ONE_TOO_MANY = [
    (10, 0, "Cannot add more than 10 items (available stock limit)"),
    (10, 3, "Cannot add more than 7 items (available stock limit)"),
    (1, 0, "Cannot add more than 1 items (available stock limit)"),
    (0, 0, "This product is out of stock."),
    (5, 5, "This product is out of stock."),
]


@pytest.mark.parametrize(("stock", "reserved"), STOCK_LEVELS)
def test_add_accepts_exactly_the_available_stock(engine: Engine, stock: int, reserved: int) -> None:
    add_product(engine, "P-100", stock=stock, reserved=reserved)

    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", stock - reserved)

    assert stored_lines(engine, BUYER_ID) == [("P-100", stock - reserved)]


@pytest.mark.parametrize(("stock", "reserved", "message"), ONE_TOO_MANY)
def test_add_refuses_one_more_than_the_available_stock(
    engine: Engine, stock: int, reserved: int, message: str
) -> None:
    add_product(engine, "P-100", stock=stock, reserved=reserved)

    with open_cart(engine) as cart, pytest.raises(CartError) as error:
        cart.add_item(BUYER_ID, "P-100", stock - reserved + 1)

    assert (error.value.code, error.value.message) == (CartErrorCode.STOCK_EXCEEDED, message)
    assert stored_lines(engine, BUYER_ID) == []


def test_adding_to_a_line_may_reach_exactly_the_available_stock(engine: Engine) -> None:
    add_product(engine, "P-100", stock=10, reserved=3)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 4)

    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 3)

    assert stored_lines(engine, BUYER_ID) == [("P-100", 7)]


@pytest.mark.parametrize(("in_cart", "adding"), [(4, 4), (7, 1)])
def test_adding_to_a_line_may_not_go_past_the_available_stock(
    engine: Engine, in_cart: int, adding: int
) -> None:
    add_product(engine, "P-100", stock=10, reserved=3)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", in_cart)

    with open_cart(engine) as cart, pytest.raises(CartError) as error:
        cart.add_item(BUYER_ID, "P-100", adding)

    assert error.value.code is CartErrorCode.STOCK_EXCEEDED
    assert stored_lines(engine, BUYER_ID) == [("P-100", in_cart)]


@pytest.mark.parametrize(("stock", "reserved"), STOCK_LEVELS)
def test_update_accepts_exactly_the_available_stock(
    engine: Engine, stock: int, reserved: int
) -> None:
    add_product(engine, "P-100", stock=stock, reserved=reserved)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 1)

    with open_cart(engine) as cart:
        cart.update_item(BUYER_ID, "P-100", stock - reserved)

    assert stored_lines(engine, BUYER_ID) == [("P-100", stock - reserved)]


@pytest.mark.parametrize(("stock", "reserved", "message"), ONE_TOO_MANY[:3])
def test_update_refuses_one_more_than_the_available_stock(
    engine: Engine, stock: int, reserved: int, message: str
) -> None:
    add_product(engine, "P-100", stock=stock, reserved=reserved)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 1)

    with open_cart(engine) as cart, pytest.raises(CartError) as error:
        cart.update_item(BUYER_ID, "P-100", stock - reserved + 1)

    assert (error.value.code, error.value.message) == (CartErrorCode.STOCK_EXCEEDED, message)
    assert stored_lines(engine, BUYER_ID) == [("P-100", 1)]


def test_update_refuses_every_quantity_once_the_stock_is_gone(engine: Engine) -> None:
    add_product(engine, "P-100", stock=5)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)
    change_product(engine, "P-100", stock_quantity=0)

    with open_cart(engine) as cart, pytest.raises(CartError) as error:
        cart.update_item(BUYER_ID, "P-100", 1)

    assert error.value.message == "This product is out of stock."
    assert stored_lines(engine, BUYER_ID) == [("P-100", 2)]


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


def bump_line_after_reading(monkeypatch: pytest.MonkeyPatch, engine: Engine, quantity: int) -> None:
    """Simulate another request that sets the line to `quantity` right after this one reads it."""
    original = cart_module.find_cart_item_for_product

    def read_then_bump(session: Session, buyer_id: int, product_id: int):
        cart_item = original(session, buyer_id, product_id)
        monkeypatch.setattr(cart_module, "find_cart_item_for_product", original)
        with Session(engine) as other_request:
            other_item = other_request.get(CartItem, cart_item.id)
            other_item.quantity = quantity
            other_request.add(other_item)
            other_request.commit()
        return cart_item

    monkeypatch.setattr(cart_module, "find_cart_item_for_product", read_then_bump)


def test_add_does_not_overwrite_an_increase_made_after_reading_the_line(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_product(engine, "P-100", stock=10)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 1)
    bump_line_after_reading(monkeypatch, engine, 3)

    with open_cart(engine) as cart:
        result = cart.add_item(BUYER_ID, "P-100", 2)

    assert result.created is False
    assert line_summary(result.cart.items) == [("P-100", 5, 500_000)]
    assert stored_lines(engine, BUYER_ID) == [("P-100", 5)]


def test_add_rechecks_stock_when_the_line_filled_up_after_reading(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_product(engine, "P-100", stock=3)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 1)
    bump_line_after_reading(monkeypatch, engine, 3)

    with open_cart(engine) as cart, pytest.raises(CartError) as error:
        cart.add_item(BUYER_ID, "P-100", 2)

    assert error.value.code is CartErrorCode.STOCK_EXCEEDED
    assert stored_lines(engine, BUYER_ID) == [("P-100", 3)]


def test_add_that_loses_an_insert_race_increases_the_new_line(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another request inserted the line after this one found none; the retry adds to it."""
    add_product(engine, "P-100")
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)
    original = cart_module.find_cart_item_for_product

    def missed_once(*args):
        monkeypatch.setattr(cart_module, "find_cart_item_for_product", original)
        return None

    monkeypatch.setattr(cart_module, "find_cart_item_for_product", missed_once)

    with open_cart(engine) as cart:
        result = cart.add_item(BUYER_ID, "P-100", 1)

    assert result.created is False
    assert stored_lines(engine, BUYER_ID) == [("P-100", 3)]


def test_add_that_keeps_losing_races_ends_in_a_controlled_conflict(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_product(engine, "P-100")
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)
    monkeypatch.setattr(cart_module, "find_cart_item_for_product", lambda *_args: None)
    monkeypatch.setattr(cart_module, "RETRY_BACKOFF_SECONDS", 0)

    with open_cart(engine) as cart:
        with pytest.raises(CartError) as error:
            cart.add_item(BUYER_ID, "P-100", 1)
        after_rollback = cart.get_cart(BUYER_ID)

    assert error.value.code is CartErrorCode.CONCURRENCY_CONFLICT
    assert line_summary(after_rollback.items) == [("P-100", 2, 200_000)]
    assert stored_lines(engine, BUYER_ID) == [("P-100", 2)]


def fail_next_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the next cart read fail once: it runs after the change was written, before commit."""
    original = cart_module.build_cart_snapshot

    def fail_once(*_args):
        monkeypatch.setattr(cart_module, "build_cart_snapshot", original)
        raise SQLAlchemyError("simulated failure after the write")

    monkeypatch.setattr(cart_module, "build_cart_snapshot", fail_once)


FAILED_CHANGES = {
    "add a new line": lambda cart: cart.add_item(BUYER_ID, "P-101", 1),
    "increase a line": lambda cart: cart.add_item(BUYER_ID, "P-100", 1),
    "update a line": lambda cart: cart.update_item(BUYER_ID, "P-100", 5),
    "remove a line": lambda cart: cart.remove_item(BUYER_ID, "P-100"),
}


@pytest.mark.parametrize("change", FAILED_CHANGES.values(), ids=FAILED_CHANGES.keys())
def test_a_change_that_fails_after_writing_is_rolled_back(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, change
) -> None:
    """The failed write must not reach the database, not even with the session's next commit."""
    for code in ("P-100", "P-101", "P-102"):
        add_product(engine, code)
    with open_cart(engine) as cart:
        cart.add_item(BUYER_ID, "P-100", 2)
    fail_next_snapshot(monkeypatch)

    with open_cart(engine) as cart:
        with pytest.raises(SQLAlchemyError):
            change(cart)
        cart.add_item(BUYER_ID, "P-102", 1)

    assert stored_lines(engine, BUYER_ID) == [("P-100", 2), ("P-102", 1)]
    assert stored_stock(engine, "P-100") == (10, 0)


@pytest.mark.parametrize(
    ("sqlite_errorcode", "lost_race"),
    [(5, True), (517, True), (6, True), (1, False), (None, False)],
)
def test_only_busy_or_locked_database_errors_count_as_a_lost_race(
    sqlite_errorcode: int | None, lost_race: bool
) -> None:
    """SQLITE_BUSY (5, or 517 for a stale snapshot) and SQLITE_LOCKED (6) are retried."""
    driver_error = SimpleNamespace(sqlite_errorcode=sqlite_errorcode)

    assert is_lost_race(OperationalError("UPDATE cart_items", {}, driver_error)) is lost_race
    assert is_lost_race(ValueError("not a database error")) is False


def test_database_allows_one_line_per_buyer_product_and_variant(engine: Engine) -> None:
    """Partial unique indexes distinguish base-product lines from variant lines."""
    product_id = add_product(engine, "P-100")

    unique_indexes = {index["name"] for index in inspect(engine).get_indexes("cart_items")}
    assert "uq_cart_items_buyer_product_base" in unique_indexes
    assert "uq_cart_items_buyer_product_variant" in unique_indexes
    with Session(engine) as session:
        session.add(CartItem(buyer_id=BUYER_ID, product_id=product_id, quantity=1))
        session.add(CartItem(buyer_id=OTHER_BUYER_ID, product_id=product_id, quantity=1))
        session.commit()
        session.add(CartItem(buyer_id=BUYER_ID, product_id=product_id, quantity=1))
        with pytest.raises(IntegrityError):
            session.commit()

    assert stored_lines(engine, BUYER_ID) == [("P-100", 1)]
    assert stored_lines(engine, OTHER_BUYER_ID) == [("P-100", 1)]


def test_product_codes_are_unique_so_each_code_has_one_line_per_buyer(engine: Engine) -> None:
    """Cart lines point to products.id; one code is one product, so (buyer, code) is unique too."""
    add_product(engine, "P-100")

    with pytest.raises(IntegrityError):
        add_product(engine, "P-100")
