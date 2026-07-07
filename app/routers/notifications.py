"""Notification API routes."""
from __future__ import annotations


from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.correlation_id import get_correlation_id
from app.schemas.base import BaseSchema, ok_response
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/v1/notifications", tags=["Notifications"])


class NotificationResponse(BaseSchema):
    """Single notification response."""

    id: str
    notification_type: str
    title: str
    message: str
    data: dict | None
    read_at: str | None
    created_at: str


class NotificationListResponse(BaseSchema):
    """List of notifications response."""

    notifications: list[NotificationResponse]
    unread_count: int
    total: int


class NotificationPreferencesResponse(BaseSchema):
    """Notification preferences response."""

    push_enabled: bool
    email_enabled: bool
    sms_enabled: bool
    transaction_notifications: bool
    security_notifications: bool
    promotional_notifications: bool


class UpdatePreferencesRequest(BaseSchema):
    """Update notification preferences request."""

    push_enabled: bool | None = None
    email_enabled: bool | None = None
    sms_enabled: bool | None = None
    transaction_notifications: bool | None = None
    security_notifications: bool | None = None
    promotional_notifications: bool | None = None


@router.get("")
async def get_notifications(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    unread_only: bool = Query(default=False),
):
    """
    Get notifications for the current user.

    Supports pagination and filtering by unread status.
    """
    correlation_id = get_correlation_id(request)
    service = NotificationService(db)

    notifications = await service.get_user_notifications(
        user_id=str(user.id),
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )

    unread_count = await service.get_unread_count(str(user.id))

    return ok_response(
        NotificationListResponse(
            notifications=[
                NotificationResponse(
                    id=str(n.id),
                    notification_type=n.notification_type,
                    title=n.title,
                    message=n.message,
                    data=n.data,
                    read_at=n.read_at.isoformat() if n.read_at else None,
                    created_at=n.created_at.isoformat(),
                )
                for n in notifications
            ],
            unread_count=unread_count,
            total=len(notifications),
        ),
        correlation_id,
    )


@router.get("/unread-count")
async def get_unread_count(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Get count of unread notifications."""
    correlation_id = get_correlation_id(request)
    service = NotificationService(db)

    count = await service.get_unread_count(str(user.id))

    return ok_response({"unread_count": count}, correlation_id)


@router.post("/{notification_id}/read")
async def mark_notification_read(
    request: Request,
    notification_id: str,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Mark a single notification as read."""
    correlation_id = get_correlation_id(request)
    service = NotificationService(db)

    success = await service.mark_read(notification_id, str(user.id))

    if not success:
        return ok_response({
            "success": False,
            "message": "Notification not found",
        }, correlation_id)

    return ok_response({"success": True}, correlation_id)


@router.post("/mark-all-read")
async def mark_all_read(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Mark all notifications as read."""
    correlation_id = get_correlation_id(request)
    service = NotificationService(db)

    count = await service.mark_all_read(str(user.id))

    return ok_response({
        "success": True,
        "marked_count": count,
    }, correlation_id)


@router.get("/preferences")
async def get_preferences(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Get notification preferences for the current user."""
    correlation_id = get_correlation_id(request)
    service = NotificationService(db)

    prefs = await service.get_or_create_preferences(str(user.id))

    return ok_response(
        NotificationPreferencesResponse(
            push_enabled=prefs.push_enabled,
            email_enabled=prefs.email_enabled,
            sms_enabled=prefs.sms_enabled,
            transaction_notifications=prefs.transaction_notifications,
            security_notifications=prefs.security_notifications,
            promotional_notifications=prefs.promotional_notifications,
        ),
        correlation_id,
    )


@router.put("/preferences")
async def update_preferences(
    request: Request,
    body: UpdatePreferencesRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Update notification preferences for the current user."""
    correlation_id = get_correlation_id(request)
    service = NotificationService(db)

    update_data = body.model_dump(exclude_none=True)
    prefs = await service.update_preferences(str(user.id), **update_data)

    return ok_response(
        NotificationPreferencesResponse(
            push_enabled=prefs.push_enabled,
            email_enabled=prefs.email_enabled,
            sms_enabled=prefs.sms_enabled,
            transaction_notifications=prefs.transaction_notifications,
            security_notifications=prefs.security_notifications,
            promotional_notifications=prefs.promotional_notifications,
        ),
        correlation_id,
    )
