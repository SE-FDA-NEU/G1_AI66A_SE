"""Atomic administrative escalation and adjudication using shared return rules."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from src.models.notification import Notification
from src.models.order import Order
from src.models.return_dispute import ReturnDispute
from src.models.return_request import ReturnRequest
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.repositories import admin_disputes as repository
from src.schemas.admin import DisputeDecisionRequest, ReturnDisputeResponse
from src.services.order_history import record_transition
from src.services.payments import pause_settlement
from src.services.returns import (
    ReturnError,
    check_return_settlement,
    restock_return_items,
    settle_return,
    sync_parent_order_state,
)

REASON_MAX_LENGTH = 500
EVIDENCE_MAX_LENGTH = 1000


def _require_admin(admin: User) -> None:
    if admin.role != "admin":
        raise ReturnError("ERR_ADMIN_REQUIRED", "An administrator account is required.", 403)
    if admin.status != "ACTIVE":
        raise ReturnError("ERR_ACCOUNT_RESTRICTED", "This account is restricted.", 403)


def _visible(value: str, label: str, limit: int) -> str:
    value = value.strip()
    if not value or len(value) > limit:
        raise ReturnError("ERR_VALIDATION", f"{label} must contain 1 to {limit} characters.", 422)
    return value


def _response(session: Session, dispute: ReturnDispute) -> ReturnDisputeResponse:
    buyer = repository.get_user(session, dispute.buyer_id)
    seller = repository.get_user(session, dispute.seller_id)
    decider = (
        repository.get_user(session, dispute.decided_by_user_id)
        if dispute.decided_by_user_id
        else None
    )
    return ReturnDisputeResponse(
        **dispute.model_dump(),
        buyer_name=buyer.name if buyer else None,
        seller_name=seller.name if seller else None,
        decided_by_name=decider.name if decider else None,
    )


def escalate_dispute(
    session: Session, admin: User, order_id: int, seller_order_id: int, reason: str, evidence: str
) -> ReturnDisputeResponse:
    """Pause the seller order and parent in the same transaction as the escalation."""
    try:
        _require_admin(admin)
        reason = _visible(reason, "Reason", REASON_MAX_LENGTH)
        evidence = _visible(evidence, "Evidence", EVIDENCE_MAX_LENGTH)
        order = repository.get_order(session, order_id)
        seller_order = repository.get_seller_order(session, seller_order_id)
        if order is None or seller_order is None:
            raise ReturnError("ERR_ORDER_NOT_FOUND", "Order or seller order not found.", 404)
        if seller_order.order_id != order.id:
            raise ReturnError(
                "ERR_SUB_ORDER_MISMATCH", "Seller order does not belong to specified order.", 400
            )
        if seller_order.status not in {"DELIVERED", "RETURN_REQUESTED"}:
            raise ReturnError(
                "ERR_INVALID_DISPUTE_STATE",
                f"Cannot escalate sub-order in status {seller_order.status} to dispute.",
                400,
            )
        if repository.existing_dispute(session, seller_order_id) is not None:
            raise ReturnError(
                "ERR_DISPUTE_EXISTS", "A dispute has already been created for this sub-order.", 409
            )
        request = repository.pending_request(session, seller_order, order)
        old_status = seller_order.status
        now = datetime.now(UTC)
        if not repository.pause_review(session, seller_order):
            raise ReturnError(
                "ERR_CONCURRENCY_CONFLICT", "The seller order changed. Refresh and retry.", 409
            )
        # Financial state remains owned by the shared US20 payment service.
        pause_settlement(session, seller_order)
        dispute = ReturnDispute(
            order_id=order.id,
            seller_order_id=seller_order.id,
            return_request_id=request.id if request else None,
            buyer_id=order.buyer_id,
            seller_id=seller_order.seller_id,
            reason=reason,
            evidence=evidence,
            created_by_user_id=admin.id,
            created_at=now,
        )
        repository.add_dispute(session, dispute)
        if old_status != "RETURN_REQUESTED":
            record_transition(
                session,
                seller_order_id=seller_order.id,
                from_status=old_status,
                to_status="RETURN_REQUESTED",
                actor=admin,
                occurred_at=now,
                note=f"Admin escalated dispute: {reason}",
            )
        sync_parent_order_state(session, order, occurred_at=now)
        session.commit()
        session.refresh(dispute)
        return _response(session, dispute)
    except IntegrityError as exc:
        session.rollback()
        if "UNIQUE constraint failed: return_disputes.seller_order_id" in str(exc.orig):
            raise ReturnError(
                "ERR_DISPUTE_EXISTS", "A dispute has already been created for this sub-order.", 409
            ) from exc
        raise
    except Exception:
        session.rollback()
        raise


def _linked_request(
    session: Session, dispute: ReturnDispute, seller_order: SellerOrder, order: Order
) -> ReturnRequest | None:
    if dispute.return_request_id is None:
        return None
    request = repository.get_request(session, dispute.return_request_id)
    if request is None or (request.seller_order_id, request.order_id, request.buyer_id) != (
        seller_order.id,
        order.id,
        order.buyer_id,
    ):
        raise ReturnError(
            "ERR_SUB_ORDER_MISMATCH", "The linked return request does not match this dispute.", 400
        )
    if request.status != "PENDING":
        raise ReturnError(
            "ERR_INVALID_TRANSITION", "The linked return request has already been resolved.", 400
        )
    return request


def adjudicate_dispute(
    session: Session, admin: User, dispute_id: int, decision: DisputeDecisionRequest
) -> ReturnDisputeResponse:
    """Claim dispute/request once, settle, audit and notify; commit only after all succeed."""
    try:
        _require_admin(admin)
        dispute = repository.get_dispute(session, dispute_id)
        if dispute is None:
            raise ReturnError("ERR_DISPUTE_NOT_FOUND", "Return dispute not found.", 404)
        if dispute.status != "PENDING":
            raise ReturnError(
                "ERR_DISPUTE_RESOLVED", "This dispute has already been adjudicated.", 400
            )
        seller_order = repository.get_seller_order(session, dispute.seller_order_id)
        order = repository.get_order(session, dispute.order_id)
        if seller_order is None or order is None:
            raise ReturnError("ERR_ORDER_NOT_FOUND", "Associated order not found.", 404)
        if (seller_order.order_id, seller_order.seller_id, order.buyer_id) != (
            order.id,
            dispute.seller_id,
            dispute.buyer_id,
        ):
            raise ReturnError(
                "ERR_SUB_ORDER_MISMATCH", "Dispute and order ownership do not match.", 400
            )
        request = _linked_request(session, dispute, seller_order, order)
        check_return_settlement(seller_order, decision.action)
        now = datetime.now(UTC)
        values = {
            "status": "APPROVED" if decision.action == "APPROVE" else "REJECTED",
            "decided_by_user_id": admin.id,
            "decided_at": now,
            "decision_notes": decision.decision_notes,
            "is_restockable": decision.is_restockable if decision.action == "APPROVE" else False,
        }
        if not repository.claim_dispute(session, dispute, values):
            raise ReturnError(
                "ERR_DISPUTE_RESOLVED", "This dispute has already been adjudicated.", 400
            )
        if request is not None and not repository.claim_request(session, request, values):
            raise ReturnError(
                "ERR_INVALID_TRANSITION",
                "The linked return request has already been resolved.",
                400,
            )
        old_status = seller_order.status
        settle_return(session, seller_order, decision.action, now, admin.id)
        if decision.action == "APPROVE" and decision.is_restockable:
            restock_return_items(session, seller_order.id)
        record_transition(
            session,
            seller_order_id=seller_order.id,
            from_status=old_status,
            to_status=seller_order.status,
            actor=admin,
            occurred_at=now,
            note=(
                f"Dispute {values['status'].lower()} by Admin {admin.name}: "
                f"{decision.decision_notes}"
            ),
        )
        sync_parent_order_state(session, order, occurred_at=now)
        action = decision.action.lower()
        repository.add_notifications(
            session,
            [
                Notification(
                    recipient_user_id=recipient,
                    order_id=order.id,
                    event_key=f"dispute:{dispute.id}:{action}:{role}",
                    message=(
                        f"Dispute for order #{order.id} was {values['status'].lower()} "
                        "by platform administration."
                    ),
                    target_path=target,
                    created_at=now,
                )
                for recipient, role, target in (
                    (order.buyer_id, "buyer", f"/orders/{order.id}"),
                    (seller_order.seller_id, "seller", "/seller/orders"),
                )
            ],
        )
        session.commit()
        session.refresh(dispute)
        return _response(session, dispute)
    except Exception:
        session.rollback()
        raise
