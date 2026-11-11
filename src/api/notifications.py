from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.auth import CurrentUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.notification import Notification
from src.services.notifications import (
    count_unread_notifications,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationResponse(BaseModel):
    id: int
    order_id: int
    message: str
    target_path: str
    created_at: datetime
    read_at: datetime | None


class NotificationListResponse(BaseModel):
    data: list[NotificationResponse]
    unread_count: int


class NotificationReadResponse(BaseModel):
    data: NotificationResponse


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int = Field(ge=0)


def _response(notification: Notification) -> NotificationResponse:
    return NotificationResponse.model_validate(notification, from_attributes=True)


@router.get("", response_model=NotificationListResponse)
def get_notifications(user: CurrentUser, session: SessionDep) -> NotificationListResponse:
    notifications, unread_count = list_notifications(session, user.id)
    return NotificationListResponse(
        data=[_response(item) for item in notifications],
        unread_count=unread_count,
    )


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
def get_unread_count(user: CurrentUser, session: SessionDep) -> NotificationUnreadCountResponse:
    return NotificationUnreadCountResponse(
        unread_count=count_unread_notifications(session, user.id),
    )


@router.post("/mark-all-read", response_model=NotificationUnreadCountResponse)
def read_all_notifications(
    user: CurrentUser, session: SessionDep,
) -> NotificationUnreadCountResponse:
    return NotificationUnreadCountResponse(
        unread_count=mark_all_notifications_read(session, user.id),
    )


@router.patch("/{notification_id}/read", response_model=NotificationReadResponse)
def read_notification(
    notification_id: int,
    user: CurrentUser,
    session: SessionDep,
) -> NotificationReadResponse:
    notification = mark_notification_read(session, user.id, notification_id)
    if notification is None:
        raise HTTPException(
            status_code=404,
            detail=error_detail("ERR_NOTIFICATION_NOT_FOUND", "Notification not found."),
        )
    return NotificationReadResponse(data=_response(notification))
