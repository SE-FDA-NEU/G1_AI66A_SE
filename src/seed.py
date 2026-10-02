from sqlmodel import Session, SQLModel, select

from src.database import engine
from src.models.product import Product


PRODUCTS = [
    Product(
        name="Wireless Mouse",
        description="Wireless mouse for study and office work",
        price=150000,
        stock_quantity=20,
    ),
    Product(
        name="Mechanical Keyboard",
        description="Mechanical keyboard for daily use",
        price=650000,
        stock_quantity=15,
    ),
    Product(
        name="Laptop Backpack",
        description="Backpack for laptops up to 15.6 inches",
        price=350000,
        stock_quantity=12,
    ),
    Product(
        name="USB-C Cable",
        description="USB-C charging cable",
        price=90000,
        stock_quantity=30,
    ),
    Product(
        name="Laptop Stand",
        description="Adjustable laptop stand",
        price=280000,
        stock_quantity=10,
    ),
    Product(
        name="Webcam",
        description="1080p webcam",
        price=420000,
        stock_quantity=8,
    ),
    Product(
        name="Desk Lamp",
        description="LED desk lamp",
        price=220000,
        stock_quantity=18,
    ),
    Product(
        name="Notebook",
        description="A5 notebook",
        price=45000,
        stock_quantity=50,
    ),
    Product(
        name="Bluetooth Speaker",
        description="Portable Bluetooth speaker",
        price=390000,
        stock_quantity=14,
    ),
    Product(
        name="Phone Stand",
        description="Adjustable phone stand",
        price=120000,
        stock_quantity=25,
    ),
]


def seed_products():
    # Fresh machine: create missing tables first
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        existing = session.exec(select(Product)).first()

        if existing:
            print("Products already exist. Seed skipped.")
            return

        session.add_all(PRODUCTS)
        session.commit()

        products = session.exec(select(Product)).all()
        print(f"Seed completed: {len(products)} products")


if __name__ == "__main__":
    seed_products()