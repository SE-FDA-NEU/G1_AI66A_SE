from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from src.auth import BuyerUser, SellerUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.product_metadata import ProductMetadata
from src.models.review import Review
from src.services.reviews import (
    ReviewError,
    create_product_review,
    list_product_reviews,
    list_reviewable_items,
    reply_to_review,
)

router = APIRouter(tags=["Reviews"])


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    order_item_id: int = Field(gt=0, strict=True)
    rating: int = Field(ge=1, le=5, strict=True)
    comment: str | None = Field(default=None, max_length=2000)
    media_url: HttpUrl | None = None


class ReviewReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reply: str = Field(min_length=1, max_length=2000)


class ReviewResponse(BaseModel):
    id: int
    rating: int
    comment: str | None
    media_url: str | None
    seller_reply: str | None
    seller_replied_at: datetime | None
    created_at: datetime


class ProductReviewList(BaseModel):
    product_code: str
    rating: float
    review_count: int
    data: list[ReviewResponse]


class ReviewCreatedResponse(BaseModel):
    data: ReviewResponse


class ReviewableItem(BaseModel):
    order_item_id: int
    quantity: int
    completed_at: datetime | None


class ReviewableItemsResponse(BaseModel):
    data: list[ReviewableItem]


def _review_response(review: Review) -> ReviewResponse:
    return ReviewResponse.model_validate(review, from_attributes=True)


def _raise_review_error(exc: ReviewError) -> HTTPException:
    return HTTPException(
        status_code=exc.status,
        detail=error_detail(exc.code, exc.message),
    )


@router.get("/products/{product_code}/reviews", response_model=ProductReviewList)
def get_product_reviews(product_code: str, session: SessionDep) -> ProductReviewList:
    try:
        product, reviews = list_product_reviews(session, product_code)
    except ReviewError as exc:
        raise _raise_review_error(exc) from exc
    metadata = session.get(ProductMetadata, product.id)
    return ProductReviewList(
        product_code=product.code,
        rating=float(metadata.rating) if metadata else 0.0,
        review_count=metadata.review_count if metadata else 0,
        data=[_review_response(review) for review in reviews],
    )


@router.post(
    "/products/{product_code}/reviews",
    response_model=ReviewCreatedResponse,
    status_code=201,
)
def post_product_review(
    product_code: str,
    request: ReviewCreate,
    buyer: BuyerUser,
    session: SessionDep,
) -> ReviewCreatedResponse:
    try:
        review = create_product_review(
            session,
            product_code,
            buyer,
            request.order_item_id,
            request.rating,
            request.comment or None,
            str(request.media_url) if request.media_url else None,
        )
        return ReviewCreatedResponse(data=_review_response(review))
    except ReviewError as exc:
        raise _raise_review_error(exc) from exc


@router.get(
    "/products/{product_code}/reviewable-items",
    response_model=ReviewableItemsResponse,
)
def get_reviewable_items(
    product_code: str,
    buyer: BuyerUser,
    session: SessionDep,
) -> ReviewableItemsResponse:
    try:
        rows = list_reviewable_items(session, product_code, buyer.id)
        return ReviewableItemsResponse(
            data=[
                ReviewableItem(
                    order_item_id=item.id,
                    quantity=item.quantity,
                    completed_at=seller_order.completed_at,
                )
                for item, seller_order in rows
                if item.id is not None
            ]
        )
    except ReviewError as exc:
        raise _raise_review_error(exc) from exc


@router.patch("/seller/reviews/{review_id}/reply", response_model=ReviewCreatedResponse)
def post_seller_reply(
    review_id: int,
    request: ReviewReplyRequest,
    seller: SellerUser,
    session: SessionDep,
) -> ReviewCreatedResponse:
    try:
        review = reply_to_review(session, seller, review_id, request.reply)
        return ReviewCreatedResponse(data=_review_response(review))
    except ReviewError as exc:
        raise _raise_review_error(exc) from exc
