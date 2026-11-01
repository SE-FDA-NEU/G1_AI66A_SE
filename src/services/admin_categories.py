"""Shared hierarchy rules and authenticated category change snapshots."""

import json
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from src.models.category import Category
from src.models.category_audit_log import CategoryAuditLog
from src.models.user import User
from src.repositories import admin_categories as repository


class CategoryError(Exception):
    def __init__(self, code: str, message: str, status: int):
        self.code, self.message, self.status = code, message, status


def validate_parent(
    session: Session, parent_id: int | None, category_id: int | None = None
) -> None:
    visited = set()
    while parent_id is not None:
        if parent_id == category_id:
            raise CategoryError(
                "ERR_CATEGORY_HIERARCHY", "A category cannot be its own ancestor.", 422
            )
        if parent_id in visited:
            raise CategoryError("ERR_CATEGORY_HIERARCHY", "The category hierarchy is invalid.", 409)
        visited.add(parent_id)
        parent = repository.get_category(session, parent_id)
        if parent is None or not parent.is_active:
            raise CategoryError("ERR_CATEGORY_PARENT", "Select an active parent category.", 422)
        parent_id = parent.parent_id


def snapshot(category: Category) -> dict:
    return category.model_dump(include={"name", "slug", "parent_id", "is_active"})


def record_action(
    session: Session,
    admin: User,
    category_id: int,
    action: str,
    before: dict | None,
    after: dict | None,
) -> None:
    if admin.role != "admin" or admin.status != "ACTIVE":
        raise CategoryError(
            "ERR_ADMIN_REQUIRED", "An active administrator account is required.", 403
        )
    if before == after:
        return
    repository.append_audit(
        session,
        CategoryAuditLog(
            category_id=category_id,
            admin_id=admin.id,
            action=action,
            before_json=json.dumps(before, ensure_ascii=False) if before is not None else None,
            after_json=json.dumps(after, ensure_ascii=False) if after is not None else None,
            created_at=datetime.now(UTC),
        ),
    )


def is_slug_conflict(error: IntegrityError) -> bool:
    # Inspect the underlying constraint, not SQL text containing unrelated column names.
    return "UNIQUE constraint failed: categories.slug" in str(error.orig)


def audit_history(session: Session, limit: int) -> list[CategoryAuditLog]:
    return repository.list_audits(session, limit)
