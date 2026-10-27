from sqlalchemy import update
from sqlmodel import Session

from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_variant import ProductVariant


def restore_order_item_stock(session: Session, item: OrderItem) -> None:
    """Restore stock to the exact inventory unit purchased, including inactive variants."""
    inventory_model = ProductVariant if item.variant_id is not None else Product
    inventory_id = item.variant_id if item.variant_id is not None else item.product_id
    session.exec(
        update(inventory_model)
        .where(inventory_model.id == inventory_id)
        .values(
            stock_quantity=inventory_model.stock_quantity + item.quantity,
            version=inventory_model.version + 1,
        )
        .execution_options(synchronize_session=False)
    )
