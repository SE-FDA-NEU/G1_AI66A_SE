"""Admin API endpoints for platform portal, catalog policy, accounts, vouchers, and disputes."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import case
from sqlmodel import select, update

from src.auth import AdminUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.account_audit_log import AccountAuditLog
from src.models.category import Category
from src.models.notification import Notification
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.return_dispute import ReturnDispute
from src.models.return_request import ReturnRequest
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.models.voucher import Voucher
from src.schemas.admin import (
    AccountAuditLogResponse,
    CategoryAdminResponse,
    CreateCategoryRequest,
    CreateVoucherRequest,
    DisputeDecisionRequest,
    ProductAdminResponse,
    ReturnDisputeResponse,
    UpdateCategoryRequest,
    UpdateProductModerationRequest,
    UpdateUserStatusRequest,
    UpdateVoucherRequest,
    UserAdminResponse,
    VoucherAdminResponse,
)
from src.services.inventory import restore_order_item_stock
from src.services.order_history import record_transition
from src.services.returns import sync_parent_order_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Portal"])


# ---------------------------------------------------------------------------
# Categories Management
# ---------------------------------------------------------------------------
@router.get("/categories", response_model=list[CategoryAdminResponse])
def admin_list_categories(
    admin: AdminUser,
    session: SessionDep,
) -> list[CategoryAdminResponse]:
    """List all categories with metadata for administrators."""
    del admin
    categories = session.exec(select(Category).order_by(Category.id)).all()
    results = []
    for cat in categories:
        count = len(
            session.exec(
                select(ProductMetadata).where(ProductMetadata.category_id == cat.id)
            ).all()
        )
        results.append(
            CategoryAdminResponse(
                id=cat.id,  # type: ignore[arg-type]
                name=cat.name,
                slug=cat.slug,
                parent_id=cat.parent_id,
                product_count=count,
            )
        )
    return results


@router.post("/categories", response_model=CategoryAdminResponse, status_code=201)
def admin_create_category(
    payload: CreateCategoryRequest,
    admin: AdminUser,
    session: SessionDep,
) -> CategoryAdminResponse:
    """Create a new product category with policy validation."""
    del admin
    slug = payload.slug.strip().lower()
    existing = session.exec(select(Category).where(Category.slug == slug)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail("ERR_CATEGORY_EXISTS", "A category with this slug already exists."),
        )

    if payload.parent_id is not None:
        parent = session.get(Category, payload.parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(
                    "ERR_PARENT_NOT_FOUND", "Specified parent category does not exist."
                ),
            )

    cat = Category(
        name=payload.name.strip(),
        slug=slug,
        parent_id=payload.parent_id,
    )
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return CategoryAdminResponse(
        id=cat.id,  # type: ignore[arg-type]
        name=cat.name,
        slug=cat.slug,
        parent_id=cat.parent_id,
        product_count=0,
    )


@router.put("/categories/{category_id}", response_model=CategoryAdminResponse)
def admin_update_category(
    category_id: int,
    payload: UpdateCategoryRequest,
    admin: AdminUser,
    session: SessionDep,
) -> CategoryAdminResponse:
    """Update a category name, slug, or parent hierarchy, validating cycles."""
    del admin
    cat = session.get(Category, category_id)
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("ERR_CATEGORY_NOT_FOUND", "Category not found."),
        )

    if payload.parent_id is not None:
        if payload.parent_id == category_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail("ERR_CATEGORY_CYCLE", "Category cannot be its own parent."),
            )
        parent = session.get(Category, payload.parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(
                    "ERR_PARENT_NOT_FOUND", "Specified parent category does not exist."
                ),
            )
        # Cycle prevention: verify target parent is not a descendant
        curr = parent
        while curr.parent_id is not None:
            if curr.parent_id == category_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_detail(
                        "ERR_CATEGORY_CYCLE", "Cannot move a category under its descendant."
                    ),
                )
            curr = session.get(Category, curr.parent_id)
            if not curr:
                break
        cat.parent_id = payload.parent_id
    elif payload.parent_id is None and "parent_id" in payload.model_fields_set:
        cat.parent_id = None

    if payload.slug is not None:
        slug = payload.slug.strip().lower()
        if slug != cat.slug:
            existing = session.exec(select(Category).where(Category.slug == slug)).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=error_detail(
                        "ERR_CATEGORY_EXISTS", "A category with this slug already exists."
                    ),
                )
            cat.slug = slug

    if payload.name is not None:
        cat.name = payload.name.strip()

    session.add(cat)
    session.commit()
    session.refresh(cat)
    count = len(
        session.exec(
            select(ProductMetadata).where(ProductMetadata.category_id == cat.id)
        ).all()
    )
    return CategoryAdminResponse(
        id=cat.id,  # type: ignore[arg-type]
        name=cat.name,
        slug=cat.slug,
        parent_id=cat.parent_id,
        product_count=count,
    )


@router.delete("/categories/{category_id}", status_code=204)
def admin_delete_category(
    category_id: int,
    admin: AdminUser,
    session: SessionDep,
) -> None:
    """Delete a category, reparenting child categories."""
    del admin
    cat = session.get(Category, category_id)
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("ERR_CATEGORY_NOT_FOUND", "Category not found."),
        )

    # Re-parent direct children to this category's parent
    children = session.exec(select(Category).where(Category.parent_id == category_id)).all()
    for child in children:
        child.parent_id = cat.parent_id
        session.add(child)

    # Unlink products referencing this category
    metas = session.exec(
        select(ProductMetadata).where(ProductMetadata.category_id == category_id)
    ).all()
    for meta in metas:
        meta.category_id = None
        session.add(meta)

    session.delete(cat)
    session.commit()


# ---------------------------------------------------------------------------
# User Account Moderation
# ---------------------------------------------------------------------------
@router.get("/users", response_model=list[UserAdminResponse])
def admin_list_users(
    admin: AdminUser,
    session: SessionDep,
    role: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    q: str | None = None,
) -> list[UserAdminResponse]:
    """List marketplace users with moderation statuses."""
    del admin
    stmt = select(User).order_by(User.id)
    if role:
        stmt = stmt.where(User.role == role)
    if status_filter:
        stmt = stmt.where(User.status == status_filter)
    users = session.exec(stmt).all()

    if q:
        query_str = q.strip().lower()
        users = [u for u in users if query_str in u.name.lower() or query_str in u.email.lower()]

    results = []
    for u in users:
        audits = session.exec(
            select(AccountAuditLog)
            .where(AccountAuditLog.user_id == u.id)
            .order_by(AccountAuditLog.created_at.desc())  # type: ignore[attr-defined]
            .limit(5)
        ).all()
        results.append(
            UserAdminResponse(
                id=u.id,  # type: ignore[arg-type]
                name=u.name,
                email=u.email,
                role=u.role,
                status=getattr(u, "status", "ACTIVE"),
                created_at=u.created_at,
                recent_audits=[
                    AccountAuditLogResponse(
                        id=a.id,  # type: ignore[arg-type]
                        user_id=a.user_id,
                        admin_id=a.admin_id,
                        action=a.action,
                        old_status=a.old_status,
                        new_status=a.new_status,
                        reason=a.reason,
                        created_at=a.created_at,
                    )
                    for a in audits
                ],
            )
        )
    return results


@router.get("/users/{user_id}", response_model=UserAdminResponse)
def admin_get_user(
    user_id: int,
    admin: AdminUser,
    session: SessionDep,
) -> UserAdminResponse:
    """Retrieve user details and audit history."""
    del admin
    u = session.get(User, user_id)
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("ERR_USER_NOT_FOUND", "User not found."),
        )
    audits = session.exec(
        select(AccountAuditLog)
        .where(AccountAuditLog.user_id == u.id)
        .order_by(AccountAuditLog.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return UserAdminResponse(
        id=u.id,  # type: ignore[arg-type]
        name=u.name,
        email=u.email,
        role=u.role,
        status=getattr(u, "status", "ACTIVE"),
        created_at=u.created_at,
        recent_audits=[
            AccountAuditLogResponse(
                id=a.id,  # type: ignore[arg-type]
                user_id=a.user_id,
                admin_id=a.admin_id,
                action=a.action,
                old_status=a.old_status,
                new_status=a.new_status,
                reason=a.reason,
                created_at=a.created_at,
            )
            for a in audits
        ],
    )


@router.patch("/users/{user_id}/status", response_model=UserAdminResponse)
def admin_update_user_status(
    user_id: int,
    payload: UpdateUserStatusRequest,
    admin: AdminUser,
    session: SessionDep,
) -> UserAdminResponse:
    """Update user account status (ACTIVE, RESTRICTED, SUSPENDED) and log the action."""
    u = session.get(User, user_id)
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("ERR_USER_NOT_FOUND", "User not found."),
        )

    if u.id == admin.id and payload.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "ERR_SELF_MODERATION",
                "Administrators cannot restrict or suspend their own account.",
            ),
        )

    old_status = getattr(u, "status", "ACTIVE")
    new_status = payload.status

    if old_status != new_status:
        u.status = new_status
        session.add(u)

        audit = AccountAuditLog(
            user_id=u.id,  # type: ignore[arg-type]
            admin_id=admin.id,  # type: ignore[arg-type]
            action="STATUS_CHANGE",
            old_status=old_status,
            new_status=new_status,
            reason=payload.reason.strip(),
            created_at=datetime.now(UTC),
        )
        session.add(audit)

        # If a seller is suspended, automatically deactivate all their active products
        if u.role == "seller" and new_status == "SUSPENDED":
            session.exec(
                update(Product)
                .where(Product.seller_id == u.id)
                .values(is_active=False)
                .execution_options(synchronize_session=False)
            )

        session.commit()
        session.refresh(u)

    return admin_get_user(user_id, admin, session)


# ---------------------------------------------------------------------------
# Platform Vouchers
# ---------------------------------------------------------------------------
@router.get("/vouchers", response_model=list[VoucherAdminResponse])
def admin_list_vouchers(
    admin: AdminUser,
    session: SessionDep,
) -> list[VoucherAdminResponse]:
    """List platform vouchers."""
    del admin
    vouchers = session.exec(
        select(Voucher)
        .where(Voucher.scope == "PLATFORM")
        .order_by(Voucher.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [
        VoucherAdminResponse(
            id=v.id,  # type: ignore[arg-type]
            code=v.code,
            scope=v.scope,
            seller_id=v.seller_id,
            discount_type=v.discount_type,
            discount_value=v.discount_value,
            max_discount=v.max_discount,
            min_order_value=v.min_order_value,
            usage_limit=v.usage_limit,
            per_user_limit=v.per_user_limit,
            used_count=v.used_count,
            starts_at=v.starts_at,
            ends_at=v.ends_at,
            is_active=v.is_active,
            created_at=v.created_at,
        )
        for v in vouchers
    ]


@router.post("/vouchers", response_model=VoucherAdminResponse, status_code=201)
def admin_create_voucher(
    payload: CreateVoucherRequest,
    admin: AdminUser,
    session: SessionDep,
) -> VoucherAdminResponse:
    """Create a validated platform-wide voucher."""
    del admin
    code = payload.code.strip().upper()
    existing = session.exec(select(Voucher).where(Voucher.code == code)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "ERR_VOUCHER_EXISTS", f"A voucher with code '{code}' already exists."
            ),
        )

    starts_at = (
        payload.starts_at.replace(tzinfo=UTC)
        if payload.starts_at.tzinfo is None
        else payload.starts_at.astimezone(UTC)
    )
    ends_at = (
        payload.ends_at.replace(tzinfo=UTC)
        if payload.ends_at.tzinfo is None
        else payload.ends_at.astimezone(UTC)
    )

    if starts_at >= ends_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "ERR_INVALID_DATES", "Voucher end date must be strictly after start date."
            ),
        )

    # Validation per discount type
    if payload.discount_type == "PERCENTAGE":
        if payload.discount_value <= 0 or payload.discount_value > 10000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(
                    "ERR_INVALID_DISCOUNT",
                    "Percentage discount value must be between 1 and 10000 bps (0.01% - 100%).",
                ),
            )
    elif payload.discount_type == "FIXED_AMOUNT":
        if payload.discount_value <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(
                    "ERR_INVALID_DISCOUNT", "Fixed amount discount must be greater than 0 ₫."
                ),
            )
    elif payload.discount_type == "FREE_SHIPPING":
        payload.discount_value = 0

    now = datetime.now(UTC)
    voucher = Voucher(
        code=code,
        scope="PLATFORM",
        seller_id=None,
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
        max_discount=payload.max_discount,
        min_order_value=payload.min_order_value,
        usage_limit=payload.usage_limit,
        per_user_limit=payload.per_user_limit,
        used_count=0,
        starts_at=starts_at,
        ends_at=ends_at,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    session.add(voucher)
    session.commit()
    session.refresh(voucher)

    return VoucherAdminResponse(
        id=voucher.id,  # type: ignore[arg-type]
        code=voucher.code,
        scope=voucher.scope,
        seller_id=voucher.seller_id,
        discount_type=voucher.discount_type,
        discount_value=voucher.discount_value,
        max_discount=voucher.max_discount,
        min_order_value=voucher.min_order_value,
        usage_limit=voucher.usage_limit,
        per_user_limit=voucher.per_user_limit,
        used_count=voucher.used_count,
        starts_at=voucher.starts_at,
        ends_at=voucher.ends_at,
        is_active=voucher.is_active,
        created_at=voucher.created_at,
    )


@router.patch("/vouchers/{voucher_id}", response_model=VoucherAdminResponse)
def admin_update_voucher(
    voucher_id: int,
    payload: UpdateVoucherRequest,
    admin: AdminUser,
    session: SessionDep,
) -> VoucherAdminResponse:
    """Update voucher status, dates, or usage limits."""
    del admin
    v = session.get(Voucher, voucher_id)
    if not v or v.scope != "PLATFORM":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("ERR_VOUCHER_NOT_FOUND", "Platform voucher not found."),
        )

    if payload.is_active is not None:
        v.is_active = payload.is_active
    if payload.usage_limit is not None:
        if payload.usage_limit < v.used_count:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(
                    "ERR_INVALID_USAGE_LIMIT",
                    "Usage limit cannot be less than already used count.",
                ),
            )
        v.usage_limit = payload.usage_limit
    if payload.per_user_limit is not None:
        v.per_user_limit = payload.per_user_limit
    if payload.ends_at is not None:
        starts_at = (
            v.starts_at.replace(tzinfo=UTC)
            if v.starts_at.tzinfo is None
            else v.starts_at.astimezone(UTC)
        )
        ends_at = (
            payload.ends_at.replace(tzinfo=UTC)
            if payload.ends_at.tzinfo is None
            else payload.ends_at.astimezone(UTC)
        )
        if ends_at <= starts_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(
                    "ERR_INVALID_DATES", "Voucher end date must be after start date."
                ),
            )
        v.ends_at = ends_at

    v.updated_at = datetime.now(UTC)
    session.add(v)
    session.commit()
    session.refresh(v)
    return VoucherAdminResponse(
        id=v.id,  # type: ignore[arg-type]
        code=v.code,
        scope=v.scope,
        seller_id=v.seller_id,
        discount_type=v.discount_type,
        discount_value=v.discount_value,
        max_discount=v.max_discount,
        min_order_value=v.min_order_value,
        usage_limit=v.usage_limit,
        per_user_limit=v.per_user_limit,
        used_count=v.used_count,
        starts_at=v.starts_at,
        ends_at=v.ends_at,
        is_active=v.is_active,
        created_at=v.created_at,
    )


# ---------------------------------------------------------------------------
# Catalog Moderation
# ---------------------------------------------------------------------------
@router.get("/products", response_model=list[ProductAdminResponse])
def admin_list_products(
    admin: AdminUser,
    session: SessionDep,
    is_active: bool | None = None,
    q: str | None = None,
) -> list[ProductAdminResponse]:
    """List all products for moderation inspection."""
    del admin
    stmt = select(Product).order_by(Product.id.desc())  # type: ignore[attr-defined]
    if is_active is not None:
        stmt = stmt.where(Product.is_active == is_active)
    products = session.exec(stmt).all()

    if q:
        query_str = q.strip().lower()
        products = [
            p for p in products
            if query_str in p.name.lower() or query_str in p.code.lower()
        ]

    results = []
    for p in products:
        seller = session.get(User, p.seller_id)
        meta = session.exec(
            select(ProductMetadata).where(ProductMetadata.product_id == p.id)
        ).first()
        category = (
            session.get(Category, meta.category_id)
            if meta and meta.category_id
            else None
        )
        results.append(
            ProductAdminResponse(
                id=p.id,  # type: ignore[arg-type]
                code=p.code,
                seller_id=p.seller_id,
                seller_name=seller.name if seller else None,
                name=p.name,
                description=p.description,
                price=p.price,
                stock_quantity=p.stock_quantity,
                is_active=p.is_active,
                is_moderated_deactivated=bool(meta.is_moderated_deactivated) if meta else False,
                category_id=category.id if category else None,
                category_name=category.name if category else None,
            )
        )
    return results


@router.patch("/products/{product_id}/status", response_model=ProductAdminResponse)
def admin_moderate_product(
    product_id: int,
    payload: UpdateProductModerationRequest,
    admin: AdminUser,
    session: SessionDep,
) -> ProductAdminResponse:
    """Deactivate or reactivate a product that violates marketplace rules."""
    del admin
    p = session.get(Product, product_id)
    if not p:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("ERR_PRODUCT_NOT_FOUND", "Product not found."),
        )

    meta = session.exec(select(ProductMetadata).where(ProductMetadata.product_id == p.id)).first()
    if not meta:
        meta = ProductMetadata(product_id=p.id)
        session.add(meta)

    if payload.is_active is False:
        meta.is_moderated_deactivated = True
        p.is_active = False
    else:
        meta.is_moderated_deactivated = False
        p.is_active = True
    p.version += 1
    session.add(p)
    session.add(meta)
    session.commit()
    session.refresh(p)
    session.refresh(meta)

    seller = session.get(User, p.seller_id)
    category = session.get(Category, meta.category_id) if meta and meta.category_id else None
    return ProductAdminResponse(
        id=p.id,  # type: ignore[arg-type]
        code=p.code,
        seller_id=p.seller_id,
        seller_name=seller.name if seller else None,
        name=p.name,
        description=p.description,
        price=p.price,
        stock_quantity=p.stock_quantity,
        is_active=p.is_active,
        is_moderated_deactivated=meta.is_moderated_deactivated,
        category_id=category.id if category else None,
        category_name=category.name if category else None,
    )


# ---------------------------------------------------------------------------
# Return Disputes Adjudication
# ---------------------------------------------------------------------------
@router.get("/disputes", response_model=list[ReturnDisputeResponse])
def admin_list_disputes(
    admin: AdminUser,
    session: SessionDep,
    status_filter: str | None = Query(None, alias="status"),
) -> list[ReturnDisputeResponse]:
    """List return/refund disputes for administrative adjudication."""
    del admin
    stmt = select(ReturnDispute).order_by(ReturnDispute.created_at.desc())  # type: ignore[attr-defined]
    if status_filter:
        stmt = stmt.where(ReturnDispute.status == status_filter)
    disputes = session.exec(stmt).all()

    results = []
    for d in disputes:
        buyer = session.get(User, d.buyer_id)
        seller = session.get(User, d.seller_id)
        decider = session.get(User, d.decided_by_user_id) if d.decided_by_user_id else None
        results.append(
            ReturnDisputeResponse(
                id=d.id,  # type: ignore[arg-type]
                order_id=d.order_id,
                seller_order_id=d.seller_order_id,
                return_request_id=d.return_request_id,
                buyer_id=d.buyer_id,
                buyer_name=buyer.name if buyer else None,
                seller_id=d.seller_id,
                seller_name=seller.name if seller else None,
                reason=d.reason,
                evidence=d.evidence,
                status=d.status,
                decision_notes=d.decision_notes,
                decided_by_user_id=d.decided_by_user_id,
                decided_by_name=decider.name if decider else None,
                is_restockable=d.is_restockable,
                created_at=d.created_at,
                decided_at=d.decided_at,
            )
        )
    return results


@router.post("/disputes", response_model=ReturnDisputeResponse, status_code=201)
def admin_create_or_escalate_dispute(
    order_id: int,
    seller_order_id: int,
    reason: str,
    evidence: str,
    admin: AdminUser,
    session: SessionDep,
) -> ReturnDisputeResponse:
    """Escalate an order into an administrative return dispute."""
    del admin
    order = session.get(Order, order_id)
    so = session.get(SellerOrder, seller_order_id)
    if not order or not so:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("ERR_ORDER_NOT_FOUND", "Order or seller order not found."),
        )

    # 1. Validate parent-child relationship
    if so.order_id != order.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "ERR_SUB_ORDER_MISMATCH", "Seller order does not belong to specified order."
            ),
        )

    # 2. Validate permitted escalation state
    if so.status not in ("RETURN_REQUESTED", "DELIVERED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "ERR_INVALID_DISPUTE_STATE",
                f"Cannot escalate sub-order in status {so.status} to dispute.",
            ),
        )

    # 3. Enforce uniqueness: only 1 dispute per seller order
    existing = session.exec(
        select(ReturnDispute).where(ReturnDispute.seller_order_id == so.id)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "ERR_DISPUTE_EXISTS", "A dispute has already been created for this sub-order."
            ),
        )

    # 4. Link to underlying return request if present
    ret_req = session.exec(
        select(ReturnRequest)
        .where(ReturnRequest.seller_order_id == so.id)
        .order_by(ReturnRequest.id.desc())
    ).first()
    return_request_id = ret_req.id if ret_req else None

    dispute = ReturnDispute(
        order_id=order.id,  # type: ignore[arg-type]
        seller_order_id=so.id,  # type: ignore[arg-type]
        return_request_id=return_request_id,
        buyer_id=order.buyer_id,
        seller_id=so.seller_id,
        reason=reason.strip(),
        evidence=evidence.strip(),
        status="PENDING",
        created_at=datetime.now(UTC),
    )
    session.add(dispute)

    # Transition sub-order to indicate pending dispute review
    so.status = "RETURN_REQUESTED"
    session.add(so)
    session.commit()
    session.refresh(dispute)

    return ReturnDisputeResponse(
        id=dispute.id,  # type: ignore[arg-type]
        order_id=dispute.order_id,
        seller_order_id=dispute.seller_order_id,
        return_request_id=dispute.return_request_id,
        buyer_id=dispute.buyer_id,
        seller_id=dispute.seller_id,
        reason=dispute.reason,
        evidence=dispute.evidence,
        status=dispute.status,
        decision_notes=None,
        decided_by_user_id=None,
        is_restockable=False,
        created_at=dispute.created_at,
        decided_at=None,
    )


@router.post("/disputes/{dispute_id}/decision", response_model=ReturnDisputeResponse)
def admin_decide_dispute(
    dispute_id: int,
    payload: DisputeDecisionRequest,
    admin: AdminUser,
    session: SessionDep,
) -> ReturnDisputeResponse:
    """Adjudicate an escalated return dispute with side effects on order and inventory."""
    dispute = session.get(ReturnDispute, dispute_id)
    if not dispute:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("ERR_DISPUTE_NOT_FOUND", "Return dispute not found."),
        )

    now = datetime.now(UTC)
    target_status = "APPROVED" if payload.action == "APPROVE" else "REJECTED"

    # Atomic conditional update on ReturnDispute to prevent duplicate adjudication
    changed = session.exec(
        update(ReturnDispute)
        .where(ReturnDispute.id == dispute_id, ReturnDispute.status == "PENDING")
        .values(
            status=target_status,
            decided_by_user_id=admin.id,
            decided_at=now,
            decision_notes=payload.decision_notes.strip(),
            is_restockable=payload.is_restockable if payload.action == "APPROVE" else False,
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "ERR_DISPUTE_RESOLVED", "This dispute has already been adjudicated."
            ),
        )

    # Link dispute to underlying ReturnRequest and close it atomically
    if dispute.return_request_id:
        session.exec(
            update(ReturnRequest)
            .where(ReturnRequest.id == dispute.return_request_id, ReturnRequest.status == "PENDING")
            .values(
                status=target_status,
                decided_by_user_id=admin.id,
                decided_at=now,
                decision_notes=payload.decision_notes.strip(),
                is_restockable=payload.is_restockable if payload.action == "APPROVE" else False,
            )
            .execution_options(synchronize_session=False)
        )

    so = session.get(SellerOrder, dispute.seller_order_id)
    order = session.get(Order, dispute.order_id)

    if so and order:
        old_status = so.status
        if payload.action == "APPROVE":
            so.status = "RETURNED_REFUNDED"
            so.payment_status = "REFUNDED"
            so.escrow_status = "REFUNDED"
            session.add(so)

            if payload.is_restockable:
                items = session.exec(
                    select(OrderItem).where(OrderItem.seller_order_id == so.id)
                ).all()
                for item in items:
                    restore_order_item_stock(session, item)
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

            record_transition(
                session,
                seller_order_id=so.id,
                from_status=old_status,
                to_status="RETURNED_REFUNDED",
                actor=admin,
                note=f"Dispute approved by Admin {admin.name}: {payload.decision_notes}",
            )
        else:
            so.status = "COMPLETED"
            so.escrow_status = "RELEASED"
            session.add(so)

            record_transition(
                session,
                seller_order_id=so.id,
                from_status=old_status,
                to_status="COMPLETED",
                actor=admin,
                note=f"Dispute rejected by Admin {admin.name}: {payload.decision_notes}",
            )

        # Sync parent order state atomically
        sync_parent_order_state(session, order)
        session.add(order)

        # Notify buyer and seller
        action_name = payload.action.lower()
        session.add(
            Notification(
                recipient_user_id=order.buyer_id,
                order_id=order.id,
                event_key=f"dispute:{dispute.id}:{action_name}:buyer",
                message=(
                    f"Dispute for order #{order.id} was {target_status.lower()} "
                    "by platform administration."
                ),
                target_path=f"/orders/{order.id}",
                created_at=now,
            )
        )
        session.add(
            Notification(
                recipient_user_id=so.seller_id,
                order_id=order.id,
                event_key=f"dispute:{dispute.id}:{action_name}:seller",
                message=(
                    f"Dispute for sub-order #{so.id} was {target_status.lower()} "
                    "by platform administration."
                ),
                target_path="/seller/orders",
                created_at=now,
            )
        )

    session.commit()
    session.refresh(dispute)

    buyer = session.get(User, dispute.buyer_id)
    seller = session.get(User, dispute.seller_id)
    return ReturnDisputeResponse(
        id=dispute.id,  # type: ignore[arg-type]
        order_id=dispute.order_id,
        seller_order_id=dispute.seller_order_id,
        return_request_id=dispute.return_request_id,
        buyer_id=dispute.buyer_id,
        buyer_name=buyer.name if buyer else None,
        seller_id=dispute.seller_id,
        seller_name=seller.name if seller else None,
        reason=dispute.reason,
        evidence=dispute.evidence,
        status=dispute.status,
        decision_notes=dispute.decision_notes,
        decided_by_user_id=dispute.decided_by_user_id,
        decided_by_name=admin.name,
        is_restockable=dispute.is_restockable,
        created_at=dispute.created_at,
        decided_at=dispute.decided_at,
    )
