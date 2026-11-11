import argparse
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import text, update
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, select

from src.auth import hash_password
from src.database import engine, init_db
from src.models.cart_item import CartItem
from src.models.category import Category
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.product_variant import ProductVariant
from src.models.review import Review
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.models.voucher import Voucher
from src.services.seller_products import CODE_PREFIX, CODE_RANDOM_BYTES

# A code in this format was assigned by generate_product_code() for a real seller-created
# listing (possibly created by the demo seller account itself) and is never a retired seed
# fixture, even though it shares the "P-" prefix with legacy codes like "P-100".
GENERATED_PRODUCT_CODE_PATTERN = re.compile(
    rf"^{re.escape(CODE_PREFIX)}[0-9A-F]{{{CODE_RANDOM_BYTES * 2}}}$"
)

DEMO_SELLER_EMAIL = "demo.seller@marketplace.local"
DEMO_BUYER_EMAIL = "user@example.com"
DEFAULT_DEV_PASSWORD = "password"
SEED_SQLITE_BUSY_TIMEOUT_MS = 30_000

SEED_CATEGORIES = [
    {"id": 1, "name": "Electronics", "slug": "electronics", "parent_slug": None},
    {"id": 2, "name": "Computer Peripherals", "slug": "peripherals", "parent_slug": "electronics"},
    {"id": 3, "name": "Keyboards & Mice", "slug": "keyboards-mice", "parent_slug": "peripherals"},
    {"id": 4, "name": "Cables & Hubs", "slug": "cables-hubs", "parent_slug": "peripherals"},
    {"id": 5, "name": "Audio & Video", "slug": "audio-video", "parent_slug": "electronics"},
    {"id": 8, "name": "Monitors", "slug": "monitors", "parent_slug": "electronics"},
    {"id": 9, "name": "Phones", "slug": "phones", "parent_slug": "electronics"},
    {"id": 10, "name": "Tablets", "slug": "tablets", "parent_slug": "electronics"},
    {"id": 11, "name": "Laptops", "slug": "laptops", "parent_slug": "electronics"},
    {"id": 6, "name": "Office & Desk", "slug": "office-desk", "parent_slug": None},
    {
        "id": 7,
        "name": "Stands & Ergonomics",
        "slug": "stands-ergonomics",
        "parent_slug": "office-desk",
    },
]

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
    {
        "name": "Platform Administrator",
        "email": "admin@example.com",
        "role": "admin",
        "password": DEFAULT_DEV_PASSWORD,
    },
]


def seed_categories(session: Session) -> dict[str, Category]:
    """Upsert standard category hierarchy, resolved by slug.

    An administrator can create a category before a later seed version adds a
    new standard one (e.g. "Monitors"/id 8) that happens to reuse that id. The
    preferred id is only used when it is still free; otherwise the row gets an
    autoincrement id and callers must resolve ids through the returned map by
    slug instead of the hardcoded values in SEED_CATEGORIES.
    """
    existing = {cat.slug: cat for cat in session.exec(select(Category)).all()}
    taken_ids = {cat.id for cat in existing.values()}
    for item in SEED_CATEGORIES:
        if item["slug"] in existing:
            continue
        parent_slug = item["parent_slug"]
        values = {
            "id": item["id"],
            "name": item["name"],
            "slug": item["slug"],
            "parent_id": existing[parent_slug].id if parent_slug else None,
        }
        if values["id"] in taken_ids:
            values.pop("id")
        session.exec(
            insert(Category).values(**values).on_conflict_do_nothing(index_elements=["slug"])
        )
        session.flush()
        inserted = session.exec(select(Category).where(Category.slug == item["slug"])).first()
        if inserted:
            existing[item["slug"]] = inserted
            taken_ids.add(inserted.id)
    return existing


def make_product(
    code: str,
    name: str,
    description: str,
    price: int,
    stock_quantity: int,
    reserved_stock: int = 0,
    seller_id: int = 1,
    image_url: str | None = None,
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
        image_url=image_url or f"/images/{code.lower()}.jpg",
        is_active=True,
        version=1,
    )


def build_products(seller_id: int = 1) -> list[Product]:
    """Build source-matched listings across peripherals and consumer devices."""
    source_images = "https://hanoicomputercdn.com/media/product/"
    products_data = [
        (
            "P-100",
            "AULA S13 Wired Gaming Mouse - Black",
            180000,
            "77136_chuot_gaming_co_day_aula_s13_mau_den_1.jpg",
        ),
        (
            "P-101",
            "AULA S100 Pro Mechanical Keyboard - 3 Mode Red Switch",
            650000,
            "https://cdn-files.hacom.vn/hacom/cdn/web/16032026/ban-phim-co-gaming-aula-s100-pro-3mode-den-xam-cam.jpg",
        ),
        (
            "AULA-003",
            "AULA F75 Ice Blue Mechanical Keyboard - Ice Vein Switch",
            1290000,
            "78915_ban_phim_co_aula_f75_ice_blue_3_mode_typec_2_4g_bluetooth_ice_vein_switch_1.jpg",
        ),
        (
            "AULA-004",
            "AULA F75 Dark Blue Mechanical Keyboard - Greywood V3",
            1290000,
            "80850_ban_phim_co_aula_f75_den_xanh_dam_cam_3_mode_grey_wood_v3_switch_1.jpg",
        ),
        (
            "AULA-005",
            "AULA F75 White Mechanical Keyboard - Red Switch",
            990000,
            "89538_ban_phim_co_gaming_co_day_aula_f75_red_switch_mau_trang_1.jpg",
        ),
        (
            "AULA-006",
            "AULA F75 Lavender Mechanical Keyboard - Greywood V3",
            1290000,
            "80852_ban_phim_co_aula_f75_tim_nhat_be_xanh_la_1.jpg",
        ),
        (
            "AULA-007",
            "AULA F75 Ice Blue Mechanical Keyboard - Reaper Switch",
            1390000,
            "78916_ban_phim_co_aula_f75_ice_blue_3_mode_typec_2_4g_bluetooth_reaper_switch_1.jpg",
        ),
        (
            "AULA-008",
            "AULA F99 White Grey Mechanical Keyboard - Greywood Switch",
            1490000,
            "77238_ban_phim_co_aula_f99_3_mode_trang_xam_typec_2_4g_bluetooth_grey_wood_switch_led_rgb_1.jpg",
        ),
        (
            "AULA-009",
            "AULA F99 Blue Purple Mechanical Keyboard - Greywood Switch",
            1490000,
            "77239_ban_phim_co_aula_f99_3_mode_trang_tim_typec_2_4g_bluetooth_grey_wood_switch_led_rgb_1.jpg",
        ),
        (
            "AULA-010",
            "AULA F87 Green Mechanical Keyboard - Greywood V3",
            1390000,
            "https://hanoicomputercdn.com/media/lib/21-10-2024/ban-phim-co-aula-f87-3-mode-den-trang-xanh-la-typec-21.png",
        ),
        (
            "AULA-011",
            "AULA F2058 Black Mechanical Keyboard - Red Switch",
            799000,
            "90722_ban_phim_co_day_gaming_aula_f2058_red_switch_mau_den_1.jpg",
        ),
        (
            "AULA-012",
            "AULA F99 Pro Grey Black Mechanical Keyboard - Nimbus V3",
            1690000,
            "86327_ban_phim_co_gaming_aula_f99_pro_3_mode_xam_den_gradient_rgb_nimbus_v3_switch_1.jpg",
        ),
        (
            "AULA-013",
            "AULA F87 Green Mechanical Keyboard - Greywood V4",
            1490000,
            "86907_ban_phim_co_gaming_aula_f87_3_mode_den_trang_xanh_la_grey_wood_v4_switch_1.jpg",
        ),
        (
            "AULA-014",
            "AULA F99 Blue Purple Mechanical Keyboard - Reaper Switch",
            1490000,
            "85172_ban_phim_co_aula_f99_xanh_duong_trang_tim_dam_1.jpg",
        ),
        (
            "AULA-015",
            "AULA F75 Grey Black Mechanical Keyboard - Reaper Switch",
            1390000,
            "86321_ban_phim_co_gaming_aula_f75_3_mode_xam_den_gradient_rgb_reaper_switch_1.jpg",
        ),
        (
            "AULA-016",
            "AULA F99 Blue Gradient Mechanical Keyboard - Star Vector",
            1590000,
            "88887_ban_phim_co_gaming_aula_f99_3_mode_den_trang_xanh_duong_gradient_star_vector_switch_1.jpg",
        ),
        (
            "AULA-017",
            "AULA F75 Purple White Mechanical Keyboard - Star Vector",
            1590000,
            "88885_ban_phim_co_aula_f75_f75_pro_3_mode_trang_tim_gradient_star_vector_switch_1.jpg",
        ),
        (
            "AULA-018",
            "AULA F99 Pro Grey Black Mechanical Keyboard - Greywood V3",
            1690000,
            "86326_ban_phim_co_gaming_aula_f99_pro_3_mode_xam_den_gradient_rgb_greywood_v3_switch_1.jpg",
        ),
        (
            "AULA-019",
            "AULA AU75 Black Grey Orange Mechanical Keyboard",
            1390000,
            "88877_ban_phim_co_gaming_aula_au75_3_mode_den_xam_cam_star_vector_switch_1.jpg",
        ),
        (
            "AULA-020",
            "AULA F108 Pro Black Pink Mechanical Keyboard",
            1790000,
            "90244_ban_phim_co_gaming_aula_f108_pro_3_mode_den_hong_grey_wood_v3_switch_1.jpg",
        ),
        (
            "AULA-021",
            "AULA F75 Max Grey Black Mechanical Keyboard",
            1590000,
            "90720_ban_phim_co_gaming_aula_f75_max_3_mode_xam_den_gradient_reaper_switch_1.jpg",
        ),
        (
            "AULA-022",
            "AULA AU75 Purple Beige Red Mechanical Keyboard",
            1390000,
            "88878_ban_phim_co_gaming_aula_au75_3_mode_tim_be_do_star_vector_switch_1.jpg",
        ),
        (
            "AULA-023",
            "AULA F75 Comic Mechanical Keyboard - Reaper Switch",
            1390000,
            "92417_ban_phim_co_gaming_aula_f75_3_mode_comic_reaper_switch.jpg",
        ),
        (
            "AULA-024",
            "AULA WIN68HE MAX Magnetic Mechanical Keyboard",
            1049000,
            "92428_ban_phim_aula_win68he_max_co_day_den_do_wing_chun_magnetic_switch.jpg",
        ),
        (
            "AULA-025",
            "AULA F108 Pro Grey Black Mechanical Keyboard",
            1790000,
            "92986_ban_phim_co_gaming_aula_f108_pro_3_mode_grey_black_gradient_nimbus_switch_1.jpg",
        ),
        (
            "AULA-026",
            "AULA M75 Blue White Orange Mechanical Keyboard",
            1590000,
            "https://hanoicomputercdn.com/media/lib/06-02-2025/ban-phim-co-gaming-aula-m75-3-mode7.jpg",
        ),
        (
            "AULA-027",
            "AULA F99 Pro Black Pink Mechanical Keyboard",
            1690000,
            "92832_ban_phim_co_gaming_aula_f99_pro_3_mode_co_num_xoay_den_hong_gradient_1.jpg",
        ),
        (
            "AULA-028",
            "AULA F108 Grey Black Mechanical Keyboard",
            1590000,
            "92835_ban_phim_co_gaming_aula_f108_3_mode_xam_den_gradient_nimbus_switch_1.jpg",
        ),
        (
            "AULA-029",
            "AULA F99 Comic Mechanical Keyboard - Greywood V3",
            1490000,
            "92840_ban_phim_co_gaming_aula_f99_3_mode_mau_comic_greywood_v3_switch.jpg",
        ),
        (
            "AULA-030",
            "AULA F75 Black Pink Mechanical Keyboard - Reaper Switch",
            1390000,
            "92830_ban_phim_co_gaming_aula_f75_3_mode_den_hong_gradient_reaper_switch_1.jpg",
        ),
        (
            "MIX-031",
            "Logitech HD C270 Webcam",
            399000,
            "https://hanoicomputercdn.com/media/product/17151_webcam_logitech_hd_c270.jpg",
        ),
        (
            "MIX-032",
            "Logitech HD C310 Webcam",
            549000,
            "https://hanoicomputercdn.com/media/product/16458_webcam_logitech_hd_webcam_c310.jpg",
        ),
        (
            "MIX-033",
            "ORICO BT2U3-10AB-GY USB 3.0 Hub - 10 Ports",
            1089000,
            "https://cdn-files.hacom.vn/hacom/cdn/web/17082026/Bo-Chia-USB-HUB-ORICO-10-cong-USB-3.0-BT2U3-10AB-GY.jpg",
        ),
        (
            "MIX-034",
            "Ergotek L234 360-Degree Laptop and Tablet Stand - Silver",
            299000,
            "https://hanoicomputercdn.com/media/product/87167_gia_do_laptop_macbook_ipad_tabblet_de_xoay_360_do_ergotek_l234_hop_kim_thep_mau_bac.jpg",
        ),
        (
            "MON-035",
            "AOC 24B36X 23.8-inch FHD IPS 144Hz Monitor",
            1990000,
            "https://cdn-files.hacom.vn/hacom/cdn/web/01012026/IMG_2901.jpg",
        ),
        (
            "MON-036",
            "AOC 27B30H 27-inch FHD IPS 120Hz Monitor",
            2399000,
            "https://hanoicomputercdn.com/media/product/90883_man_hinh_aoc_27b30h_new3.jpg",
        ),
        (
            "PHONE-037",
            "Samsung Galaxy A17 5G 8GB/128GB Phone - Black",
            5749000,
            "https://cdn-files.hacom.vn/hacom/cdn/web/23032026/Dien-thoai-Samsung-Galaxy-A17-5G-8GB128GB-Den-SM-A176BDS-1.jpg",
        ),
        (
            "PHONE-038",
            "Samsung Galaxy A17 5G 8GB/128GB Phone - Blue",
            5749000,
            "https://cdn-files.hacom.vn/hacom/cdn/web/21072026/Dien-thoai-Samsung-Galaxy-A17-5G-8GB128GB-Xanh-SM-A176BDS-1.jpg",
        ),
        (
            "TAB-039",
            "Xiaomi Pad 7 8GB/128GB WiFi Tablet - Blue",
            9199000,
            "https://cdn-files.hacom.vn/hacom/cdn/web/24112025/may-tinh-bang-xiaomi-pad-7-8gb128gb-wifi-mtbx0007_0001_Layer-2.jpg",
        ),
        (
            "TAB-040",
            "Xiaomi Pad 7 8GB/128GB WiFi Tablet - Gray",
            9199000,
            "https://cdn-files.hacom.vn/hacom/cdn/web/26112025/may-tinh-bang-xiaomi-pad-7-8gb128gb-wifi-mtbx0016_0001_xiaomi-2.jpg",
        ),
        (
            "LAP-041",
            "ASUS VivoBook S3407QA-SF043W 14-inch OLED Laptop",
            21490000,
            "https://cdn-files.hacom.vn/hacom/cdn/web/15062026/Laptop-Asus-VivoBook-S3407QA-SF043W-X1-26-100-16GB-RAM-D5X-512GB-SSD-14-OLED-W6E-BT-Win11SL-Xam-1.jpg",
        ),
        (
            "LAP-042",
            "Lenovo V14 G5 83HD0062VA 14-inch Laptop",
            20990000,
            "https://cdn-files.hacom.vn/hacom/cdn/web/07112025/laptop-lenovo-v14-g5-83hd005kva-ltlv0290_0007_lnv1.jpg",
        ),
        (
            "LAP-043",
            "HP Pavilion 15-eg3035TX 15.6-inch Laptop",
            20990000,
            "https://hanoicomputercdn.com/media/product/75771_laptop_hp_pavilion_15_eg3035tx__8u6l7pa___4_.jpg",
        ),
        (
            "PHONE-044",
            "Apple iPhone 15 128GB Phone - Blue (MTP43VN/A)",
            17499000,
            "https://cdn-files.hacom.vn/hacom//web/Dien-thoai-di-dong-iPhone-15-128GB-Blue-MTP43VNA-1.jpg",
        ),
        (
            "TAB-045",
            "Apple iPad A16 Gen 11 5G 128GB Tablet - Blue (MD7G4ZA/A)",
            16199000,
            "https://cdn-files.hacom.vn/hacom/cdn/web/20102025/may-tinh-bang-apple-ipad-a16-gen-11-5g-mtbp0304_0002_Layer-2.jpg",
        ),
        (
            "MON-046",
            "LG 27MK600M-B 27-inch FHD IPS Monitor",
            3289000,
            "https://hanoicomputercdn.com/media/product/45488_lg_27mk600m__4_.png",
        ),
        (
            "MON-047",
            "LG 24MK600M-B 23.8-inch FHD IPS Monitor",
            2899000,
            "https://hanoicomputercdn.com/media/product/44319_lg_24mk600m__4_.png",
        ),
    ]

    products: list[Product] = []

    for index, (code, name, price, image_path) in enumerate(products_data):
        image_url = image_path if image_path.startswith("http") else source_images + image_path
        products.append(
            make_product(
                code=code,
                seller_id=seller_id,
                name=name,
                description=f"{name}. Source-matched product listing from HACOM.",
                price=price,
                stock_quantity=12 + (index % 19),
                reserved_stock=0 if index % 5 else 2,
                image_url=image_url,
            )
        )

    return products


def seed_product_metadata(
    session: Session, products: list[Product], categories: dict[str, Category]
) -> None:
    """Populate discovery metadata, categories, ratings and sales for sample products.

    Synthetic ratings, sales counts, and demo timestamps are ONLY assigned to the sample
    catalog products. Any non-sample product without metadata receives clean default
    metadata (0.0 rating, 0 sales, current UTC timestamp).

    `categories` must be the slug-keyed map returned by `seed_categories`: category ids
    are not guaranteed to match SEED_CATEGORIES when an id was already taken.
    """
    category_code_map = {
        "MON": categories["monitors"].id,
        "PHONE": categories["phones"].id,
        "TAB": categories["tablets"].id,
        "LAP": categories["laptops"].id,
    }
    category_keyword_map = [
        (("Monitor", "Screen", "Display"), categories["monitors"].id),
        (("Phone", "Galaxy", "iPhone"), categories["phones"].id),
        (("Tablet", "Pad", "iPad"), categories["tablets"].id),
        (("Mouse", "Keyboard", "Keypad", "Wrist Rest"), categories["keyboards-mice"].id),
        (
            ("Cable", "Hub", "Adapter", "Flash Drive", "Memory Card", "Case", "Organizer"),
            categories["cables-hubs"].id,
        ),
        (
            ("Webcam", "Speaker", "Earbuds", "Headphone", "Microphone", "Sound Card", "Light"),
            categories["audio-video"].id,
        ),
        (("Stand", "Cooling Pad", "Tripod"), categories["stands-ergonomics"].id),
        (("Power Bank", "Charging Pad"), categories["electronics"].id),
    ]
    office_desk_id = categories["office-desk"].id

    def resolve_category(pname: str) -> int:
        for keywords, cat_id in category_keyword_map:
            if any(kw.lower() in pname.lower() for kw in keywords):
                return cat_id
        return office_desk_id  # Office & Desk default

    # The supplied list can include user-created products; only catalog fixtures
    # may receive synthetic metrics and timestamps.
    sample_codes = {p.code for p in build_products()}

    for index, product in enumerate(products):
        if product.id is None:
            continue
        is_sample = product.code in sample_codes
        code_prefix = product.code.split("-", 1)[0]
        cat_id = None
        if is_sample:
            cat_id = category_code_map.get(code_prefix) or resolve_category(product.name)
        rating_val = round(3.5 + ((index * 3) % 15) * 0.1, 1) if is_sample else 0.0
        sales_val = (((index * 23 + 17) % 350) + 5) if is_sample else 0
        created_dt = (DEMO_DATE - timedelta(hours=index * 6)) if is_sample else datetime.now(UTC)

        session.exec(
            insert(ProductMetadata)
            .values(
                product_id=product.id,
                category_id=cat_id,
                rating=rating_val,
                review_count=0,
                sales_count=sales_val,
                created_at=created_dt,
            )
            .on_conflict_do_nothing(index_elements=["product_id"])
        )
        existing_meta = session.get(ProductMetadata, product.id)
        if existing_meta and is_sample and existing_meta.category_id is None:
            existing_meta.category_id = cat_id
            session.add(existing_meta)


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


def cleanup_legacy_catalog(session: Session, source_codes: set[str], seller_id: int) -> None:
    """Remove unused demo-seller fixtures while preserving every other seller's data.

    `Product.code.like("P-%")` also matches real listings created through the Seller
    API, including ones created by the demo seller account itself. Those always use
    generate_product_code()'s format and must be filtered out before anything here
    is deleted or deactivated.
    """
    legacy_products = session.exec(
        select(Product).where(
            Product.code.not_in(source_codes),
            (Product.code.like("P-%")),
            Product.seller_id == seller_id,
        )
    ).all()
    legacy_products = [
        product
        for product in legacy_products
        if not GENERATED_PRODUCT_CODE_PATTERN.match(product.code)
    ]
    for product in legacy_products:
        has_order = (
            session.exec(select(OrderItem.id).where(OrderItem.product_id == product.id)).first()
            is not None
        )
        has_cart = (
            session.exec(select(CartItem.id).where(CartItem.product_id == product.id)).first()
            is not None
        )
        has_variant = (
            session.exec(
                select(ProductVariant.id).where(ProductVariant.product_id == product.id)
            ).first()
            is not None
        )
        has_review = (
            session.exec(select(Review.id).where(Review.product_id == product.id)).first()
            is not None
        )
        if has_order or has_cart or has_variant or has_review:
            product.is_active = False
            session.add(product)
            continue
        # ProductMetadata has an ON DELETE CASCADE foreign key; deleting only
        # the parent avoids scheduling the same metadata row twice in SQLite.
        session.delete(product)


def _seed_catalog(session: Session) -> tuple[int, int, int]:
    categories = seed_categories(session)
    seller = get_or_create_demo_seller(session)
    sample_products = build_products(seller_id=seller.id)
    added = 0
    for product in sample_products:
        result = session.exec(
            insert(Product)
            .values(**product.model_dump(exclude={"id"}))
            .on_conflict_do_nothing(index_elements=["code"])
        )
        added += result.rowcount

    # Keep the two demo listings synchronized for databases created before the
    # catalog adopted the external product names and images. This is limited to
    # the original seed names and never overwrites a seller's later edits.
    legacy_catalog_updates = {
        "P-100": (
            "Wireless Mouse",
            "AULA S13 Wired Gaming Mouse - Black",
            "AULA S13 wired gaming mouse with RGB lighting and USB connection.",
            "https://hanoicomputercdn.com/media/product/77136_chuot_gaming_co_day_aula_s13_mau_den_1.jpg",
        ),
        "P-101": (
            "Mechanical Keyboard",
            "AULA S100 Pro Mechanical Keyboard - 3 Mode Red Switch",
            "AULA S100 Pro mechanical keyboard with 3-mode connection and Red switch.",
            "https://cdn-files.hacom.vn/hacom/cdn/web/16032026/ban-phim-co-gaming-aula-s100-pro-3mode-den-xam-cam.jpg",
        ),
    }
    for code, (legacy_name, name, description, image_url) in legacy_catalog_updates.items():
        existing = session.exec(select(Product).where(Product.code == code)).first()
        if existing and existing.name == legacy_name:
            existing.name = name
            existing.description = description
            existing.image_url = image_url
            session.add(existing)

    sample_codes = [p.code for p in sample_products]
    for seeded in sample_products:
        existing = session.exec(select(Product).where(Product.code == seeded.code)).first()
        if existing and existing.seller_id == seller.id and existing.name == seeded.name:
            # Refresh source links for unchanged seed rows without overwriting seller edits.
            existing.description = seeded.description
            existing.image_url = seeded.image_url
            session.add(existing)
    # Scenario fixtures have a different lifecycle from the base catalog.
    preserved_codes = set(sample_codes) | {row[0] for row in DEMO_PRODUCTS}
    cleanup_legacy_catalog(session, preserved_codes, seller.id)
    seeded_products = session.exec(
        select(Product).where(Product.code.in_(sample_codes)).order_by(Product.id.asc())
    ).all()
    seed_product_metadata(session, seeded_products, categories)

    # Initialize clean default metadata for any existing products without metadata
    existing_without_metadata = session.exec(
        select(Product)
        .outerjoin(ProductMetadata, Product.id == ProductMetadata.product_id)
        .where(ProductMetadata.product_id.is_(None))
    ).all()
    for prod in existing_without_metadata:
        session.exec(
            insert(ProductMetadata)
            .values(
                product_id=prod.id,
                category_id=None,
                rating=0.0,
                review_count=0,
                sales_count=0,
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["product_id"])
        )

    all_products = session.exec(select(Product)).all()
    return added, len(all_products), sum(product.is_active for product in all_products)


def _run_seed(catalog: bool, demo: bool):
    """Migrate first; serialize SQLite writers and commit all requested fixtures once."""
    if engine.dialect.name == "sqlite":
        # Concurrent first-time seeds must wait for the complete initialization
        # and seed transaction instead of failing at SQLite's five-second default.
        with engine.connect() as connection:
            connection.exec_driver_sql(f"PRAGMA busy_timeout={SEED_SQLITE_BUSY_TIMEOUT_MS}")
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

# Demo vouchers with diverse codes, scopes, and discount types for checkout testing
DEMO_VOUCHERS: list[dict] = [
    # --- Platform vouchers (applies to total order) ---
    {
        "code": "PLATFORM10",
        "scope": "PLATFORM",
        "discount_type": "PERCENTAGE",
        "discount_value": 1000,  # 10% (in basis points)
        "max_discount": 50_000,
        "min_order_value": 100_000,
        "usage_limit": 100,
        "per_user_limit": 2,
    },
    {
        "code": "SAVE50K",
        "scope": "PLATFORM",
        "discount_type": "FIXED_AMOUNT",
        "discount_value": 50_000,
        "max_discount": None,
        "min_order_value": 300_000,
        "usage_limit": 50,
        "per_user_limit": 1,
    },
    {
        "code": "PLATFORM20",
        "scope": "PLATFORM",
        "discount_type": "PERCENTAGE",
        "discount_value": 2000,  # 20%
        "max_discount": 100_000,
        "min_order_value": 500_000,
        "usage_limit": 30,
        "per_user_limit": 1,
    },
    # --- Free-shipping vouchers (platform scope, FREE_SHIPPING type) ---
    {
        "code": "FREESHIP",
        "scope": "PLATFORM",
        "discount_type": "FREE_SHIPPING",
        "discount_value": 0,
        "max_discount": None,
        "min_order_value": 0,
        "usage_limit": 200,
        "per_user_limit": 3,
    },
    {
        "code": "FREESHIPVIP",
        "scope": "PLATFORM",
        "discount_type": "FREE_SHIPPING",
        "discount_value": 0,
        "max_discount": None,
        "min_order_value": 500_000,
        "usage_limit": 50,
        "per_user_limit": 1,
    },
    # --- Shop vouchers (seller-scoped, applies to seller order) ---
    # Demo Seller 1 (demo.seller@marketplace.local)
    {
        "code": "SHOP15",
        "scope": "SHOP",
        "discount_type": "PERCENTAGE",
        "discount_value": 1500,  # 15%
        "max_discount": 75_000,
        "min_order_value": 150_000,
        "usage_limit": 50,
        "per_user_limit": 1,
        "_seller_email": DEMO_SELLER_EMAIL,
    },
    {
        "code": "SHOP30K",
        "scope": "SHOP",
        "discount_type": "FIXED_AMOUNT",
        "discount_value": 30_000,
        "max_discount": None,
        "min_order_value": 200_000,
        "usage_limit": 40,
        "per_user_limit": 1,
        "_seller_email": DEMO_SELLER_EMAIL,
    },
    # Seller 2 (seller@example.com)
    {
        "code": "SHOP2DEAL",
        "scope": "SHOP",
        "discount_type": "PERCENTAGE",
        "discount_value": 500,  # 5%
        "max_discount": 20_000,
        "min_order_value": 50_000,
        "usage_limit": 100,
        "per_user_limit": 2,
        "_seller_email": "seller@example.com",
    },
    {
        "code": "WELCOME20K",
        "scope": "SHOP",
        "discount_type": "FIXED_AMOUNT",
        "discount_value": 20_000,
        "max_discount": None,
        "min_order_value": 0,
        "usage_limit": None,
        "per_user_limit": 1,
        "_seller_email": "seller@example.com",
    },
]


def seed_demo_vouchers(session: Session, users: dict[str, User]) -> int:
    """Upsert demo vouchers by code; skip any code that already exists.

    Returns the number of vouchers newly inserted.
    """
    now = datetime.now(UTC)
    starts = datetime(2026, 1, 1, tzinfo=UTC)
    ends = datetime(2027, 12, 31, 23, 59, 59, tzinfo=UTC)
    inserted = 0
    for entry in DEMO_VOUCHERS:
        code = entry["code"]
        if session.exec(select(Voucher).where(Voucher.code == code)).first():
            continue
        seller_id: int | None = None
        if entry.get("_seller_email"):
            seller = users.get(entry["_seller_email"])
            if seller is None:
                continue
            seller_id = seller.id
        voucher = Voucher(
            code=code,
            scope=entry["scope"],
            seller_id=seller_id,
            discount_type=entry["discount_type"],
            discount_value=entry["discount_value"],
            max_discount=entry.get("max_discount"),
            min_order_value=entry.get("min_order_value", 0),
            usage_limit=entry.get("usage_limit"),
            per_user_limit=entry.get("per_user_limit"),
            used_count=0,
            is_active=True,
            starts_at=starts,
            ends_at=ends,
            created_at=now,
            updated_at=now,
        )
        session.add(voucher)
        inserted += 1
    return inserted


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
    categories = seed_categories(session)
    demo_sales_map = {
        "P-DEMO-PENDING": 1,
        "P-DEMO-PROCESS": 2,
        "P-DEMO-COMPLETE": 3,
        "P-DEMO-CANCEL": 0,
        "P-DEMO-CART": 0,
        "P-DEMO-OUT": 0,
    }
    for code, product in products.items():
        if product.id is not None:
            existing_meta = session.get(ProductMetadata, product.id)
            if not existing_meta:
                session.add(
                    ProductMetadata(
                        product_id=product.id,
                        category_id=categories["office-desk"].id,
                        rating=4.0,
                        sales_count=demo_sales_map.get(code, 0),
                        created_at=DEMO_DATE,
                    )
                )
    seed_demo_vouchers(session, users)
    return True


def seed_vouchers() -> int:
    """Standalone seeding function for demo vouchers."""
    init_db()
    with Session(engine) as session, session.begin():
        users = seed_users(session)
        inserted = seed_demo_vouchers(session, users)
    return inserted


def seed_demo_scenarios() -> bool:
    _, created, _ = _run_seed(catalog=False, demo=True)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the catalog, demo scenarios, and test vouchers."
    )
    parser.add_argument(
        "--demo", action="store_true", help="Add carts, sample orders, and vouchers once"
    )
    parser.add_argument(
        "--vouchers", action="store_true", help="Add test vouchers with different codes"
    )
    args = parser.parse_args()
    counts, created, total = _run_seed(catalog=True, demo=args.demo)
    _print_catalog(counts)
    if args.demo:
        print(
            "Demo scenarios: added" if created else "Demo scenarios: already installed (unchanged)"
        )
        print(f"Products after demo seed: {total}")
    if args.vouchers:
        num = seed_vouchers()
        print(f"Test vouchers: {num} newly inserted ({len(DEMO_VOUCHERS)} total available)")


if __name__ == "__main__":
    main()
