"""Category and discovery metadata API endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import select

from src.auth import AdminUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.category import Category

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/categories", tags=["Categories"])

CATEGORIES_ERROR_MESSAGE = "Unable to load categories right now. Please try again later."


class CategoryResponse(BaseModel):
    """Public category representation."""

    id: int
    name: str
    slug: str
    parent_id: int | None = None
    is_active: bool = True


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    parent_id: int | None = Field(default=None, ge=1)


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    parent_id: int | None = Field(default=None, ge=1)
    is_active: StrictBool | None = None


class SellerSummaryResponse(BaseModel):
    """Public seller representation for filter selection."""

    id: int
    name: str


@router.get("", response_model=list[CategoryResponse])
def list_categories(session: SessionDep) -> list[CategoryResponse]:
    """Return all categories for navigation and filter controls."""
    try:
        categories = session.exec(
            select(Category).where(Category.is_active.is_(True)).order_by(Category.id)
        ).all()
        return [
            CategoryResponse(
                id=cat.id,  # type: ignore[arg-type]
                name=cat.name,
                slug=cat.slug,
                parent_id=cat.parent_id,
                is_active=cat.is_active,
            )
            for cat in categories
            if cat.id is not None
        ]
    except SQLAlchemyError as exc:
        logger.exception("Failed to query categories")
        raise HTTPException(
            status_code=500,
            detail=error_detail("ERR_DATABASE_FAILURE", CATEGORIES_ERROR_MESSAGE),
        ) from exc


@router.get("/admin", response_model=list[CategoryResponse])
def list_admin_categories(_admin: AdminUser, session: SessionDep) -> list[CategoryResponse]:
    """Return active and inactive categories for administrator management."""
    try:
        categories = session.exec(select(Category).order_by(Category.id)).all()
    except SQLAlchemyError as exc:
        logger.exception("Failed to query categories for administration")
        raise HTTPException(
            status_code=500,
            detail=error_detail("ERR_DATABASE_FAILURE", CATEGORIES_ERROR_MESSAGE),
        ) from exc
    return [
        CategoryResponse(
            id=category.id,
            name=category.name,
            slug=category.slug,
            parent_id=category.parent_id,
            is_active=category.is_active,
        )
        for category in categories
        if category.id is not None
    ]


def _validate_parent(session, parent_id: int | None, category_id: int | None = None) -> None:
    if parent_id is None:
        return
    visited: set[int] = set()
    current_id = parent_id
    while current_id is not None:
        if current_id == category_id:
            raise HTTPException(
                status_code=422,
                detail=error_detail(
                    "ERR_CATEGORY_HIERARCHY", "A category cannot be its own ancestor."
                ),
            )
        if current_id in visited:
            raise HTTPException(
                status_code=409,
                detail=error_detail("ERR_CATEGORY_HIERARCHY", "The category hierarchy is invalid."),
            )
        visited.add(current_id)
        parent = session.get(Category, current_id)
        if parent is None or not parent.is_active:
            raise HTTPException(
                status_code=422,
                detail=error_detail("ERR_CATEGORY_PARENT", "Select an active parent category."),
            )
        current_id = parent.parent_id


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryCreate, _admin: AdminUser, session: SessionDep
) -> CategoryResponse:
    _validate_parent(session, body.parent_id)
    category = Category(name=body.name, slug=body.slug, parent_id=body.parent_id)
    try:
        session.add(category)
        session.commit()
        session.refresh(category)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=error_detail("ERR_CATEGORY_SLUG", "That category slug is already in use."),
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("Failed to create category")
        raise HTTPException(
            status_code=500, detail=error_detail("ERR_DATABASE_FAILURE", CATEGORIES_ERROR_MESSAGE)
        ) from exc
    return CategoryResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        parent_id=category.parent_id,
        is_active=category.is_active,
    )


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int = Path(gt=0),
    body: CategoryUpdate = ...,
    _admin: AdminUser = ...,
    session: SessionDep = ...,
) -> CategoryResponse:
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=404, detail=error_detail("ERR_CATEGORY_NOT_FOUND", "Category not found.")
        )
    if "parent_id" in body.model_fields_set:
        _validate_parent(session, body.parent_id, category_id)
        category.parent_id = body.parent_id
    if body.name is not None:
        category.name = body.name
    if body.slug is not None:
        category.slug = body.slug
    if body.is_active is not None:
        if body.is_active:
            _validate_parent(session, category.parent_id, category_id)
        else:
            has_active_children = session.exec(
                select(Category.id).where(
                    Category.parent_id == category_id,
                    Category.is_active.is_(True),
                )
            ).first()
            if has_active_children is not None:
                raise HTTPException(
                    status_code=409,
                    detail=error_detail(
                        "ERR_CATEGORY_HAS_CHILDREN", "Deactivate child categories first."
                    ),
                )
        category.is_active = body.is_active
    try:
        session.add(category)
        session.commit()
        session.refresh(category)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=error_detail("ERR_CATEGORY_SLUG", "That category slug is already in use."),
        ) from exc
    return CategoryResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        parent_id=category.parent_id,
        is_active=category.is_active,
    )


@router.delete("/{category_id}", response_model=CategoryResponse)
def deactivate_category(
    category_id: int, _admin: AdminUser, session: SessionDep
) -> CategoryResponse:
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=404, detail=error_detail("ERR_CATEGORY_NOT_FOUND", "Category not found.")
        )
    has_active_children = session.exec(
        select(Category.id).where(Category.parent_id == category_id, Category.is_active.is_(True))
    ).first()
    if has_active_children is not None:
        raise HTTPException(
            status_code=409,
            detail=error_detail("ERR_CATEGORY_HAS_CHILDREN", "Deactivate child categories first."),
        )
    category.is_active = False
    session.add(category)
    session.commit()
    return CategoryResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        parent_id=category.parent_id,
        is_active=False,
    )
