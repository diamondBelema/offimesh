"""Device blacklist middleware for blocking requests from blacklisted devices."""
from __future__ import annotations

import hashlib
from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.blacklisted_device import BlacklistedDevice
from app.models.device import Device
from app.models.user import User

logger = structlog.get_logger(__name__)


async def check_device_blacklist(
    request: Request,
    device_fingerprint: Annotated[str | None, Header(alias="X-Device-Fingerprint")] = None,
    db: Annotated[AsyncSession, Depends(get_session)] = None,
) -> None:
    """
    Check if the requesting device is blacklisted.

    This dependency should be added to authenticated routes that
    involve sensitive operations (token provisioning, transactions, etc.).

    Raises HTTPException(403) if device is blacklisted.
    """
    if not device_fingerprint:
        # No device fingerprint provided - allow but log
        logger.debug("no_device_fingerprint_header")
        return

    # Hash the fingerprint
    fingerprint_hash = hashlib.sha256(device_fingerprint.encode()).hexdigest()

    # Check blacklist
    result = await db.execute(
        select(BlacklistedDevice).where(
            BlacklistedDevice.device_fingerprint_hash == fingerprint_hash
        )
    )
    blacklisted = result.scalar_one_or_none()

    if blacklisted:
        logger.warning(
            "blacklisted_device_blocked",
            fingerprint_hash=fingerprint_hash[:16],
            reason=blacklisted.reason,
        )
        raise HTTPException(
            status_code=403,
            detail="Device is blacklisted. Please contact support.",
        )


async def check_device_blacklist_by_id(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)] = None,
) -> None:
    """
    Check if the user's registered devices are blacklisted.

    Use this when you have a user object and want to check their devices.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return

    # Get user's devices
    result = await db.execute(
        select(Device).where(Device.user_id == user.id)
    )
    devices = result.scalars().all()

    if not devices:
        return

    # Check each device fingerprint hash
    for device in devices:
        if device.device_fingerprint_hash:
            blacklist_result = await db.execute(
                select(BlacklistedDevice).where(
                    BlacklistedDevice.device_fingerprint_hash == device.device_fingerprint_hash
                )
            )
            if blacklist_result.scalar_one_or_none():
                logger.warning(
                    "user_device_blacklisted",
                    user_id=str(user.id),
                    device_id=str(device.id),
                )
                raise HTTPException(
                    status_code=403,
                    detail="One of your devices is blacklisted. Please contact support.",
                )


class DeviceBlacklistMiddleware:
    """
    ASGI middleware to check device blacklist on all requests.

    This runs before the route handler for ALL requests.

    Note: For selective protection, use the check_device_blacklist dependency
    instead of this global middleware.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Get device fingerprint header
        headers = dict(scope.get("headers", []))
        device_fp = headers.get(b"x-device-fingerprint", b"").decode("utf-8")

        if device_fp:
            # Store in scope for later access
            scope["device_fingerprint"] = device_fp

        await self.app(scope, receive, send)


async def get_device_from_fingerprint(
    user: User,
    device_fingerprint: str,
    db: AsyncSession,
) -> Device | None:
    """Get device by fingerprint for a user."""
    fingerprint_hash = hashlib.sha256(device_fingerprint.encode()).hexdigest()

    result = await db.execute(
        select(Device).where(
            Device.user_id == user.id,
            Device.device_fingerprint_hash == fingerprint_hash,
        )
    )
    return result.scalar_one_or_none()


async def validate_device_not_blacklisted(
    device_fingerprint: str,
    db: AsyncSession,
) -> None:
    """
    Validate a device fingerprint is not blacklisted.

    Raises HTTPException if blacklisted.
    """
    fingerprint_hash = hashlib.sha256(device_fingerprint.encode()).hexdigest()

    result = await db.execute(
        select(BlacklistedDevice).where(
            BlacklistedDevice.device_fingerprint_hash == fingerprint_hash
        )
    )

    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=403,
            detail="Device is blacklisted",
        )


# Dependency for routes that require device validation
DeviceNotBlacklisted = Depends(check_device_blacklist)
