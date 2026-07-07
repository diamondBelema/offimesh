"""Notification service for sending alerts and updates to users."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationPreference
from app.repositories.audit_repository import AuditRepository

logger = structlog.get_logger(__name__)

# Notification types
NOTIFICATION_TYPES = {
    "transaction_received": {"title": "Payment Received", "category": "transaction"},
    "transaction_sent": {"title": "Payment Sent", "category": "transaction"},
    "transaction_failed": {"title": "Payment Failed", "category": "transaction"},
    "token_provisioned": {"title": "Offline Token Created", "category": "transaction"},
    "token_expiring": {"title": "Token Expiring Soon", "category": "transaction"},
    "token_expired": {"title": "Token Expired", "category": "transaction"},
    "security_pin_changed": {"title": "PIN Changed", "category": "security"},
    "security_new_device": {"title": "New Device Added", "category": "security"},
    "security_suspicious_activity": {"title": "Suspicious Activity", "category": "security"},
    "identity_verified": {"title": "Identity Verified", "category": "security"},
    "identity_rejected": {"title": "Identity Verification Failed", "category": "security"},
    "device_blacklisted": {"title": "Device Blocked", "category": "security"},
    "wallet_funded": {"title": "Wallet Funded", "category": "transaction"},
    "withdrawal_complete": {"title": "Withdrawal Complete", "category": "transaction"},
    "welcome": {"title": "Welcome to OffiMesh", "category": "promotional"},
}


class NotificationService:
    """
    Service for managing and sending user notifications.

    Notifications are stored in PostgreSQL and pushed via Supabase Realtime.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.audit_repo = AuditRepository(db)

    async def send_notification(
        self,
        user_id: str | uuid.UUID,
        notification_type: str,
        title: str | None = None,
        message: str | None = None,
        data: dict | None = None,
        correlation_id: str | None = None,
    ) -> Notification:
        """
        Send a notification to a user.

        Args:
            user_id: Target user ID
            notification_type: Type from NOTIFICATION_TYPES
            title: Override default title
            message: Custom message
            data: Additional data payload
            correlation_id: Request correlation ID

        Returns:
            Created notification
        """
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

        # Check if user has preferences and wants this type
        should_send = await self._check_preference(user_uuid, notification_type)
        if not should_send:
            logger.info(
                "notification_skipped_by_preference",
                user_id=str(user_uuid),
                type=notification_type,
            )
            return None

        # Get default title if not provided
        type_info = NOTIFICATION_TYPES.get(notification_type, {})
        final_title = title or type_info.get("title", "Notification")
        if message is None:
            message = f"You have a new notification: {final_title}"

        # Create notification
        notification = Notification(
            user_id=user_uuid,
            notification_type=notification_type,
            title=final_title,
            message=message,
            data=data,
        )
        self.db.add(notification)
        await self.db.flush()

        logger.info(
            "notification_created",
            notification_id=str(notification.id),
            user_id=str(user_uuid),
            type=notification_type,
        )

        # Push to Supabase Realtime would happen here via trigger
        # The client subscribes to the notifications table

        return notification

    async def _check_preference(
        self,
        user_id: uuid.UUID,
        notification_type: str,
    ) -> bool:
        """Check if user wants to receive this notification type."""
        result = await self.db.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )
        pref = result.scalar_one_or_none()

        if pref is None:
            # Default preferences - allow transaction and security, skip promotional
            type_info = NOTIFICATION_TYPES.get(notification_type, {})
            category = type_info.get("category", "transaction")
            return category != "promotional"

        type_info = NOTIFICATION_TYPES.get(notification_type, {})
        category = type_info.get("category", "transaction")

        if category == "transaction":
            return pref.transaction_notifications
        elif category == "security":
            return pref.security_notifications
        elif category == "promotional":
            return pref.promotional_notifications

        return True

    async def mark_read(
        self,
        notification_id: str | uuid.UUID,
        user_id: str | uuid.UUID,
    ) -> bool:
        """Mark a notification as read."""
        notification_uuid = uuid.UUID(notification_id) if isinstance(notification_id, str) else notification_id
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

        result = await self.db.execute(
            select(Notification).where(
                Notification.id == notification_uuid,
                Notification.user_id == user_uuid,
            )
        )
        notification = result.scalar_one_or_none()

        if not notification:
            return False

        notification.read_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True

    async def mark_all_read(self, user_id: str | uuid.UUID) -> int:
        """Mark all notifications as read for a user."""
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

        result = await self.db.execute(
            select(Notification).where(
                Notification.user_id == user_uuid,
                Notification.read_at.is_(None),
            )
        )
        notifications = result.scalars().all()

        now = datetime.now(timezone.utc)
        for n in notifications:
            n.read_at = now

        await self.db.flush()
        return len(notifications)

    async def get_unread_count(self, user_id: str | uuid.UUID) -> int:
        """Get count of unread notifications."""
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

        from sqlalchemy import func
        result = await self.db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_uuid,
                Notification.read_at.is_(None),
            )
        )
        return result.scalar() or 0

    async def get_user_notifications(
        self,
        user_id: str | uuid.UUID,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> list[Notification]:
        """Get notifications for a user."""
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

        query = select(Notification).where(Notification.user_id == user_uuid)

        if unread_only:
            query = query.where(Notification.read_at.is_(None))

        query = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_or_create_preferences(
        self,
        user_id: str | uuid.UUID,
    ) -> NotificationPreference:
        """Get or create notification preferences for a user."""
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

        result = await self.db.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_uuid)
        )
        pref = result.scalar_one_or_none()

        if pref is None:
            pref = NotificationPreference(user_id=user_uuid)
            self.db.add(pref)
            await self.db.flush()

        return pref

    async def update_preferences(
        self,
        user_id: str | uuid.UUID,
        **kwargs,
    ) -> NotificationPreference:
        """Update notification preferences."""
        pref = await self.get_or_create_preferences(user_id)

        for key, value in kwargs.items():
            if hasattr(pref, key):
                setattr(pref, key, value)

        pref.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return pref

    # Convenience methods for common notifications

    async def notify_transaction_received(
        self,
        user_id: str,
        amount_kobo: int,
        sender_name: str | None = None,
        tx_id: str | None = None,
        correlation_id: str | None = None,
    ) -> Notification:
        """Notify user of received payment."""
        amount_naira = amount_kobo / 100
        sender = sender_name or "Someone"
        message = f"You received {amount_naira:,.2f} from {sender}"

        return await self.send_notification(
            user_id=user_id,
            notification_type="transaction_received",
            message=message,
            data={"tx_id": tx_id, "amount_kobo": amount_kobo, "sender": sender_name},
            correlation_id=correlation_id,
        )

    async def notify_token_expiring(
        self,
        user_id: str,
        token_id: str,
        remaining_kobo: int,
        minutes_until_expiry: int,
        correlation_id: str | None = None,
    ) -> Notification:
        """Notify user that their offline token is expiring."""
        remaining_naira = remaining_kobo / 100
        message = f"Your offline token has {remaining_naira:,.2f} remaining and expires in {minutes_until_expiry} minutes"

        return await self.send_notification(
            user_id=user_id,
            notification_type="token_expiring",
            message=message,
            data={
                "token_id": token_id,
                "remaining_kobo": remaining_kobo,
                "minutes_until_expiry": minutes_until_expiry,
            },
            correlation_id=correlation_id,
        )

    async def notify_security_alert(
        self,
        user_id: str,
        alert_type: str,
        details: str,
        data: dict | None = None,
        correlation_id: str | None = None,
    ) -> Notification:
        """Send a security notification."""
        return await self.send_notification(
            user_id=user_id,
            notification_type="security_suspicious_activity",
            title=f"Security Alert: {alert_type}",
            message=details,
            data=data,
            correlation_id=correlation_id,
        )
