"""Return and refund request endpoints."""

from fastapi import APIRouter, HTTPException, status

from src.auth import CurrentUser
from src.database import SessionDep
from src.errors import error_detail
from src.schemas.returns import (
    CreateReturnRequest,
    ReturnDecisionRequest,
    ReturnRequestListResponse,
    ReturnRequestResponse,
)
from src.services.returns import (
    ReturnError,
    decide_return_request,
    get_return_request,
    list_order_return_requests,
    submit_return_request,
)

router = APIRouter(tags=["Returns"])


@router.post(
    "/orders/{order_id}/returns",
    response_model=ReturnRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_return_request_endpoint(
    order_id: int,
    payload: CreateReturnRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> ReturnRequestResponse:
    """Submit a return or refund request for a delivered order."""
    if current_user.role != "buyer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail("ERR_BUYER_REQUIRED", "A buyer account is required."),
        )
    try:
        data = submit_return_request(session, current_user, order_id, payload)
        return ReturnRequestResponse(data=data)
    except ReturnError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail=error_detail(exc.code, exc.message),
        ) from exc


@router.get(
    "/orders/{order_id}/returns",
    response_model=ReturnRequestListResponse,
)
def list_return_requests_endpoint(
    order_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> ReturnRequestListResponse:
    """List return requests associated with an order."""
    try:
        items = list_order_return_requests(session, current_user, order_id)
        return ReturnRequestListResponse(data=items)
    except ReturnError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail=error_detail(exc.code, exc.message),
        ) from exc


@router.get(
    "/return-requests/{return_request_id}",
    response_model=ReturnRequestResponse,
)
def get_return_request_endpoint(
    return_request_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> ReturnRequestResponse:
    """Get details of a specific return request."""
    try:
        data = get_return_request(session, current_user, return_request_id)
        return ReturnRequestResponse(data=data)
    except ReturnError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail=error_detail(exc.code, exc.message),
        ) from exc


@router.post(
    "/return-requests/{return_request_id}/decision",
    response_model=ReturnRequestResponse,
)
def decide_return_request_endpoint(
    return_request_id: int,
    decision: ReturnDecisionRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> ReturnRequestResponse:
    """Approve or reject a return request."""
    try:
        data = decide_return_request(session, current_user, return_request_id, decision)
        return ReturnRequestResponse(data=data)
    except ReturnError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail=error_detail(exc.code, exc.message),
        ) from exc
