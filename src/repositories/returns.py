"""Persistence for the shared conditional return-restock rule; no commit."""

from sqlalchemy import case, update
from sqlmodel import Session, select

from src.models.order_item import OrderItem
from src.models.product_metadata import ProductMetadata


def purchased_items(session: Session, seller_order_id: int) -> list[OrderItem]:
    return list(
        session.exec(select(OrderItem).where(OrderItem.seller_order_id == seller_order_id)).all()
    )


def reduce_sold_count(session: Session, item: OrderItem) -> None:
    session.exec(
        update(ProductMetadata)
        .where(ProductMetadata.product_id == item.product_id)
        .values(
            sales_count=case(
                (ProductMetadata.sales_count - item.quantity < 0, 0),
                else_=ProductMetadata.sales_count - item.quantity,
            )
        )
        .execution_options(synchronize_session=False)
    )
