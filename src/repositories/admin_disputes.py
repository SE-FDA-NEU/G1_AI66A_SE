"""Admin dispute queries and conditional claims; the service owns commit/rollback."""

from sqlalchemy import update
from sqlmodel import Session, select

from src.models.notification import Notification
from src.models.order import Order
from src.models.return_dispute import ReturnDispute
from src.models.return_request import ReturnRequest
from src.models.seller_order import SellerOrder
from src.models.user import User


def get_order(session: Session, order_id: int) -> Order | None:
    return session.get(Order, order_id)


def get_seller_order(session: Session, seller_order_id: int) -> SellerOrder | None:
    return session.get(SellerOrder, seller_order_id)


def get_dispute(session: Session, dispute_id: int) -> ReturnDispute | None:
    return session.get(ReturnDispute, dispute_id)


def existing_dispute(session: Session, seller_order_id: int) -> ReturnDispute | None:
    return session.exec(
        select(ReturnDispute).where(ReturnDispute.seller_order_id == seller_order_id)
    ).first()


def pending_request(
    session: Session, seller_order: SellerOrder, order: Order
) -> ReturnRequest | None:
    return session.exec(
        select(ReturnRequest).where(
            ReturnRequest.seller_order_id == seller_order.id,
            ReturnRequest.order_id == order.id,
            ReturnRequest.buyer_id == order.buyer_id,
            ReturnRequest.status == "PENDING",
        )
    ).first()


def get_request(session: Session, request_id: int) -> ReturnRequest | None:
    return session.get(ReturnRequest, request_id)


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def pause_review(session: Session, seller_order: SellerOrder) -> bool:
    result = session.exec(
        update(SellerOrder)
        .where(
            SellerOrder.id == seller_order.id,
            SellerOrder.status == seller_order.status,
            SellerOrder.escrow_status == seller_order.escrow_status,
            SellerOrder.payment_status == seller_order.payment_status,
        )
        .values(status="RETURN_REQUESTED")
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 1:
        session.refresh(seller_order)
        return True
    return False


def add_dispute(session: Session, dispute: ReturnDispute) -> None:
    session.add(dispute)
    session.flush()


def claim_dispute(session: Session, dispute: ReturnDispute, values: dict) -> bool:
    result = session.exec(
        update(ReturnDispute)
        .where(
            ReturnDispute.id == dispute.id,
            ReturnDispute.status == "PENDING",
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def claim_request(session: Session, request: ReturnRequest, values: dict) -> bool:
    result = session.exec(
        update(ReturnRequest)
        .where(
            ReturnRequest.id == request.id,
            ReturnRequest.status == "PENDING",
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def add_notifications(session: Session, rows: list[Notification]) -> None:
    session.add_all(rows)
