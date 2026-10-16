"""A throwaway cart database for the cart service and API tests.

Each test builds its own SQLite file, so no test sees rows left by another and the shared
in-memory database of `conftest.py` is never touched. Results are read back through a new
session, never from objects a service still holds.
"""

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

import src.models  # noqa: F401  (registers every table on SQLModel.metadata)
from src.models.cart_item import CartItem
from src.models.product import Product
from src.models.user import User

SELLER_ID = 1
BUYER_ID = 2
OTHER_BUYER_ID = 3


def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


def create_cart_engine(db_path: Path) -> Engine:
    """A fresh database file with one seller and two buyers."""
    engine = create_engine(f"sqlite:///{db_path}")
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
    return engine


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
