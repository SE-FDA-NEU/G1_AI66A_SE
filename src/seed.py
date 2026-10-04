from sqlmodel import Session, select

from src.database import engine, init_db
from src.models.product import Product
from src.models.user import User

DEMO_SELLER_EMAIL = "demo.seller@marketplace.local"


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


def get_or_create_demo_seller(session: Session) -> User:
    """Return the demo seller, creating it when it does not exist."""
    seller = session.exec(
        select(User).where(User.email == DEMO_SELLER_EMAIL)
    ).first()

    if seller is None:
        seller = User(
            name="Demo Seller",
            email=DEMO_SELLER_EMAIL,
            role="seller",
        )
        session.add(seller)
        session.flush()

    return seller


def seed_products() -> None:
    """Create missing tables and seed the sample catalog."""
    init_db()

    with Session(engine) as session:
        seller = get_or_create_demo_seller(session)

        if seller.id is None:
            raise RuntimeError("Demo seller could not be created.")

        products = build_products(seller_id=seller.id)

        existing_products = session.exec(select(Product)).all()
        existing_codes = {
            product.code for product in existing_products
        }

        new_products = [
            product
            for product in products
            if product.code not in existing_codes
        ]

        if new_products:
            session.add_all(new_products)

        session.commit()

        all_products = session.exec(select(Product)).all()

        active_products = [
            product
            for product in all_products
            if product.is_active
        ]

        print(f"Added: {len(new_products)} products")
        print(f"Total products: {len(all_products)}")
        print(f"Active products: {len(active_products)}")


if __name__ == "__main__":
    seed_products()
