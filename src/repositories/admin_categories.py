"""Category/audit persistence; callers own the transaction."""

from sqlmodel import Session, select

from src.models.category import Category
from src.models.category_audit_log import CategoryAuditLog


def get_category(session: Session, category_id: int) -> Category | None:
    return session.get(Category, category_id)


def append_audit(session: Session, audit: CategoryAuditLog) -> None:
    session.add(audit)


def list_audits(session: Session, limit: int) -> list[CategoryAuditLog]:
    return list(
        session.exec(
            select(CategoryAuditLog)
            .order_by(CategoryAuditLog.created_at.desc(), CategoryAuditLog.id.desc())
            .limit(limit)
        ).all()
    )
