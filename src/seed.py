import argparse
from datetime import UTC, datetime

from sqlalchemy import text, update
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, select

from src.auth import hash_password
from src.database import engine, init_db
from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.seller_order import SellerOrder
from src.models.user import User

DEMO_SELLER_EMAIL = "demo.seller@marketplace.local"
DEMO_BUYER_EMAIL = "user@example.com"
DEFAULT_DEV_PASSWORD = "password"

SEED_USERS: list[dict[str, str]] = [
    {
        "name": "Demo Seller",
        "email": DEMO_SELLER_EMAIL,
        "role": "seller",
        "password": DEFAULT_DEV_PASSWORD,
    },
    {
        "name": "Demo Seller (Example)",
        "email": "seller@example.com",
        "role": "seller",
        "password": DEFAULT_DEV_PASSWORD,
    },
    {
        "name": "Demo Buyer",
        "email": DEMO_BUYER_EMAIL,
        "role": "buyer",
        "password": DEFAULT_DEV_PASSWORD,
    },
    {
        "name": "Demo Buyer (Local)",
        "email": "demo.buyer@marketplace.local",
        "role": "buyer",
        "password": DEFAULT_DEV_PASSWORD,
    },
]


def make_product(
    code: str,
    name: str,
    description: str,
    price: int,
    stock_quantity: int,
    reserved_stock: int = 0,
    seller_id: int = 1,
) -> Product:
    """Create one product linked to an existing seller."""
    return Product(
        code=code,
        seller_id=seller_id,
        name=name,
        description=description,
        price=price,
        stock_quantity=stock_quantity,
        reserved_stock=reserved_stock,
        image_url=f"/images/{code.lower()}.jpg",
        is_active=True,
        version=1,
    )


def build_products(seller_id: int = 1) -> list[Product]:
    """Build the sample product catalog."""
    products_data = [
        ("Wireless Mouse", "Wireless mouse for study and office work", 180000),
        ("Mechanical Keyboard", "Mechanical keyboard with tactile switches", 650000),
        ("USB-C Cable", "USB-C charging and data cable", 90000),
        ("Laptop Stand", "Adjustable aluminium laptop stand", 280000),
        ("Webcam", "1080p webcam for online meetings", 420000),
        ("Bluetooth Speaker", "Portable Bluetooth speaker", 390000),
        ("Phone Stand", "Adjustable desktop phone stand", 120000),
        ("USB-C Charger", "Fast USB-C wall charger", 180000),
        ("Wireless Earbuds", "Bluetooth wireless earbuds", 450000),
        ("Power Bank", "Portable high-capacity power bank", 350000),
        ("HDMI Cable", "HDMI cable for monitor connection", 110000),
        ("Mouse Pad", "Non-slip mouse pad for desk use", 70000),
        ("USB Hub", "Multi-port USB hub", 260000),
        ("Portable SSD Case", "Protective case for portable SSD", 140000),
        ("Tablet Stand", "Adjustable stand for tablets", 160000),
        ("Keyboard Wrist Rest", "Comfortable keyboard wrist rest", 130000),
        ("Gaming Mouse", "Ergonomic gaming mouse", 320000),
        ("Wireless Keyboard", "Compact wireless keyboard", 390000),
        ("USB Microphone", "USB microphone for calls and streaming", 520000),
        ("Headphone Stand", "Desktop stand for headphones", 150000),
        ("Laptop Cooling Pad", "Cooling pad with USB-powered fans", 330000),
        ("Bluetooth Mouse", "Compact Bluetooth mouse", 210000),
        ("USB Flash Drive 32GB", "Portable 32GB USB flash drive", 120000),
        ("USB Flash Drive 64GB", "Portable 64GB USB flash drive", 180000),
        ("Memory Card Reader", "USB memory card reader", 160000),
        ("Ethernet Adapter", "USB-C to Ethernet network adapter", 280000),
        ("USB-C to HDMI Adapter", "USB-C video output adapter", 310000),
        ("Wireless Presenter", "Wireless presentation clicker", 270000),
        (
            "Noise Cancelling Headphones",
            "Over-ear Bluetooth headphones",
            890000,
        ),
        ("Mini Bluetooth Keyboard", "Portable Bluetooth keyboard", 350000),
        ("Smartphone Tripod", "Compact tripod for smartphones", 230000),
        ("Webcam Cover", "Sliding privacy cover for webcams", 50000),
        ("Cable Organizer", "Desktop cable management organizer", 80000),
        ("Screen Cleaning Kit", "Cleaning kit for displays and devices", 95000),
        ("USB Extension Cable", "USB extension cable", 85000),
        ("Laptop Privacy Filter", "Privacy screen filter for laptops", 370000),
        ("Wireless Charging Pad", "Qi wireless charging pad", 290000),
        ("USB Desk Fan", "Compact USB-powered desk fan", 170000),
        (
            "Portable Bluetooth Receiver",
            "Bluetooth audio receiver",
            220000,
        ),
        (
            "Computer Cleaning Brush",
            "Soft brush for keyboards and devices",
            65000,
        ),
        ("USB Numeric Keypad", "External USB numeric keypad", 190000),
        ("USB Sound Card", "External USB audio adapter", 180000),
        ("Laptop Webcam Light", "USB light for video calls", 250000),
        (
            "Portable Monitor Stand",
            "Foldable stand for portable monitors",
            240000,
        ),
        (
            "USB-C Multiport Adapter",
            "USB-C adapter with HDMI and USB ports",
            490000,
        ),
    ]

    products: list[Product] = []

    for index, (name, description, price) in enumerate(products_data):
        code_number = 100 + index

        products.append(
            make_product(
                code=f"P-{code_number}",
                seller_id=seller_id,
                name=name,
                description=description,
                price=price,
                stock_quantity=12 + (index % 19),
                reserved_stock=0 if index % 5 else 2,
            )
        )

    return products


def seed_users(session: Session) -> dict[str, User]:
    """Upsert by email without resetting passwords or account ownership."""
    users = {}
    for entry in SEED_USERS:
        user = session.exec(select(User).where(User.email == entry["email"])).first()
        if user is None:
            session.exec(
                insert(User)
                .values(
                    name=entry["name"],
                    email=entry["email"],
                    role=entry["role"],
                    password_hash=hash_password(entry["password"]),
                )
                .on_conflict_do_nothing(index_elements=["email"])
            )
            user = session.exec(select(User).where(User.email == entry["email"])).one()
        if user.role != entry["role"]:
            raise RuntimeError("A demo account exists with a different role; seed rolled back.")
        if not user.password_hash:
            session.exec(
                update(User)
                .where(User.id == user.id, User.password_hash == "")
                .values(password_hash=hash_password(entry["password"]))
            )
            session.refresh(user)
        users[entry["email"]] = user
    return users


def get_or_create_demo_seller(session: Session) -> User:
    return seed_users(session)[DEMO_SELLER_EMAIL]


def _seed_catalog(session: Session) -> tuple[int, int, int]:
    seller = get_or_create_demo_seller(session)
    added = 0
    for product in build_products(seller_id=seller.id):
        result = session.exec(
            insert(Product)
            .values(**product.model_dump(exclude={"id"}))
            .on_conflict_do_nothing(index_elements=["code"])
        )
        added += result.rowcount
    products = session.exec(select(Product)).all()
    return added, len(products), sum(product.is_active for product in products)


def _run_seed(catalog: bool, demo: bool):
    """Migrate first; serialize SQLite writers and commit all requested fixtures once."""
    init_db()
    with Session(engine) as session, session.begin():
        # This project uses SQLite. Taking the write lock before checking marker
        # and natural keys also prevents two seed processes from racing each other.
        session.exec(text("BEGIN IMMEDIATE"))
        counts = _seed_catalog(session) if catalog else None
        created = _seed_demo_scenarios(session) if demo else False
        total = len(session.exec(select(Product)).all())
    return counts, created, total


def _print_catalog(counts: tuple[int, int, int]) -> None:
    added, total, active = counts
    print(f"Added: {added} products")
    print(f"Total products: {total}")
    print(f"Active products: {active}")


def seed_products() -> None:
    counts, _, _ = _run_seed(catalog=True, demo=False)
    _print_catalog(counts)


DEMO_MARKER = "seed84:PENDING"
DEMO_DATE = datetime(2026, 10, 10, 12, tzinfo=UTC)
DEMO_PRODUCTS = (
    ("P-DEMO-CART", "Demo cart item", DEMO_SELLER_EMAIL, 100_000, 12),
    ("P-DEMO-PENDING", "Demo pending item", DEMO_SELLER_EMAIL, 150_000, 9),
    ("P-DEMO-PROCESS", "Demo processing item", "seller@example.com", 200_000, 8),
    ("P-DEMO-COMPLETE", "Demo completed item", DEMO_SELLER_EMAIL, 250_000, 7),
    ("P-DEMO-CANCEL", "Demo cancelled item", "seller@example.com", 300_000, 10),
    ("P-DEMO-OUT", "Demo out-of-stock item", "seller@example.com", 50_000, 0),
)
DEMO_ORDERS = (
    ("PENDING", "P-DEMO-PENDING", 1),
    ("PROCESSING", "P-DEMO-PROCESS", 2),
    ("COMPLETED", "P-DEMO-COMPLETE", 3),
    ("CANCELLED", "P-DEMO-CANCEL", 1),
)


def _seed_demo_scenarios(session: Session) -> bool:
    """Install scenarios and marker in the caller's transaction; preserve edits on rerun."""
    if session.exec(select(Order.id).where(Order.request_key == DEMO_MARKER)).first():
        return False
    users = seed_users(session)
    for entry in SEED_USERS:
        if users[entry["email"]].role != entry["role"]:
            raise RuntimeError("A demo account exists with a different role; no scenarios added.")
    codes = [entry[0] for entry in DEMO_PRODUCTS]
    if session.exec(select(Product.id).where(Product.code.in_(codes))).first():
        raise RuntimeError(
            "Demo product codes already exist without the marker; no scenarios added."
        )
    buyer = users[DEMO_BUYER_EMAIL]
    products = {}
    for code, name, seller_email, price, stock in DEMO_PRODUCTS:
        product = make_product(
            code, name, "Issue #84 demo fixture", price, stock, seller_id=users[seller_email].id
        )
        # Orders below already represent purchased units; stock is the final
        # physical balance, not a second live checkout stock deduction.
        if code in {"P-DEMO-PENDING", "P-DEMO-PROCESS", "P-DEMO-COMPLETE"}:
            product.version = 2
        elif code == "P-DEMO-CANCEL":
            product.version = 3
        session.add(product)
        session.flush()
        products[code] = product
    session.add(
        CartItem(
            buyer_id=buyer.id,
            product_id=products["P-DEMO-CART"].id,
            quantity=2,
            price_at_add=products["P-DEMO-CART"].price,
            created_at=DEMO_DATE,
        )
    )
    for status, code, quantity in DEMO_ORDERS:
        product = products[code]
        parent = Order(
            buyer_id=buyer.id,
            total_amount=product.price * quantity,
            status=status,
            recipient_name="Demo Buyer",
            delivery_address="123 Demo Street",
            phone_number="0900000000",
            request_key=f"seed84:{status}",
            created_at=DEMO_DATE,
        )
        session.add(parent)
        session.flush()
        child = SellerOrder(
            order_id=parent.id,
            seller_id=product.seller_id,
            status=status,
            created_at=DEMO_DATE,
            completed_at=DEMO_DATE if status == "COMPLETED" else None,
        )
        session.add(child)
        session.flush()
        session.add(
            OrderItem(
                seller_order_id=child.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=product.price,
            )
        )
    return True


def seed_demo_scenarios() -> bool:
    _, created, _ = _run_seed(catalog=False, demo=True)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the catalog and optional P0 demo scenarios.")
    parser.add_argument("--demo", action="store_true", help="Add carts and sample orders once")
    args = parser.parse_args()
    counts, created, total = _run_seed(catalog=True, demo=args.demo)
    _print_catalog(counts)
    if args.demo:
        print(
            "Demo scenarios: added" if created else "Demo scenarios: already installed (unchanged)"
        )
        print(f"Products after demo seed: {total}")


if __name__ == "__main__":
    main()
