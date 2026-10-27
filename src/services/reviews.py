from datetime import UTC, datetime

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.review import Review
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.services.notifications import create_notification


class ReviewError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def list_product_reviews(session: Session, product_code: str) -> tuple[Product, list[Review]]:
    product = session.exec(select(Product).where(Product.code == product_code)).first()
    if product is None:
        raise ReviewError("ERR_PRODUCT_NOT_FOUND", "Product not found.", 404)
    reviews = session.exec(
        select(Review)
        .where(Review.product_id == product.id)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .limit(100)
    ).all()
    return product, reviews


def list_reviewable_items(
    session: Session, product_code: str, buyer_id: int
) -> list[tuple[OrderItem, SellerOrder]]:
    product = session.exec(select(Product).where(Product.code == product_code)).first()
    if product is None:
        raise ReviewError("ERR_PRODUCT_NOT_FOUND", "Product not found.", 404)
    return session.exec(
        select(OrderItem, SellerOrder)
        .join(SellerOrder, SellerOrder.id == OrderItem.seller_order_id)
        .join(Order, Order.id == SellerOrder.order_id)
        .outerjoin(Review, Review.order_item_id == OrderItem.id)
        .where(
            Order.buyer_id == buyer_id,
            OrderItem.product_id == product.id,
            SellerOrder.status == "COMPLETED",
            Review.id.is_(None),
        )
        .order_by(SellerOrder.completed_at.desc(), OrderItem.id.desc())
    ).all()


def create_product_review(
    session: Session,
    product_code: str,
    buyer: User,
    order_item_id: int,
    rating: int,
    comment: str | None,
    media_url: str | None,
) -> Review:
    row = session.exec(
        select(OrderItem, SellerOrder, Order, Product)
        .join(SellerOrder, SellerOrder.id == OrderItem.seller_order_id)
        .join(Order, Order.id == SellerOrder.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.id == order_item_id, Product.code == product_code)
    ).first()
    if row is None:
        raise ReviewError("ERR_REVIEW_NOT_ELIGIBLE", "This purchase cannot be reviewed.", 404)
    item, seller_order, order, product = row
    if order.buyer_id != buyer.id:
        raise ReviewError("ERR_REVIEW_NOT_ELIGIBLE", "This purchase cannot be reviewed.", 404)
    if seller_order.status != "COMPLETED":
        raise ReviewError("ERR_REVIEW_NOT_COMPLETED", "The order item is not completed.", 409)
    if session.exec(select(Review.id).where(Review.order_item_id == item.id)).first() is not None:
        raise ReviewError(
            "ERR_REVIEW_ALREADY_EXISTS",
            "This order item has already been reviewed.",
            409,
        )

    review = Review(
        order_item_id=item.id,
        product_id=product.id,
        buyer_id=buyer.id,
        rating=rating,
        comment=comment,
        media_url=media_url,
    )
    try:
        session.add(review)
        session.flush()

        if session.get(ProductMetadata, product.id) is None:
            session.add(
                ProductMetadata(
                    product_id=product.id,
                    rating=0,
                    review_count=0,
                    sales_count=0,
                )
            )
            session.flush()

        average_rating = (
            select(func.avg(Review.rating))
            .where(Review.product_id == product.id)
            .scalar_subquery()
        )
        review_count = (
            select(func.count(Review.id))
            .where(Review.product_id == product.id)
            .scalar_subquery()
        )
        session.exec(
            update(ProductMetadata)
            .where(ProductMetadata.product_id == product.id)
            .values(rating=average_rating, review_count=review_count)
            .execution_options(synchronize_session=False)
        )
        create_notification(
            session,
            recipient_user_id=product.seller_id,
            order_id=order.id,
            event_key=f"review:{review.id}:created",
            message=f"A buyer reviewed {product.name}.",
            target_path=f"/products/{product.code}",
        )
        session.commit()
        session.refresh(review)
        return review
    except IntegrityError as exc:
        session.rollback()
        existing = session.exec(
            select(Review.id).where(Review.order_item_id == order_item_id)
        ).first()
        if existing is not None:
            raise ReviewError(
                "ERR_REVIEW_ALREADY_EXISTS",
                "This order item has already been reviewed.",
                409,
            ) from exc
        raise
    except Exception:
        session.rollback()
        raise


def reply_to_review(
    session: Session,
    seller: User,
    review_id: int,
    reply: str,
) -> Review:
    row = session.exec(
        select(Review, Product)
        .join(Product, Product.id == Review.product_id)
        .where(Review.id == review_id)
    ).first()
    if row is None:
        raise ReviewError("ERR_REVIEW_NOT_FOUND", "Review not found.", 404)
    review, product = row
    if product.seller_id != seller.id:
        raise ReviewError("ERR_RESOURCE_OWNER", "You do not own this product.", 403)
    review.seller_reply = reply
    review.seller_replied_at = datetime.now(UTC)
    session.add(review)
    session.commit()
    session.refresh(review)
    return review
