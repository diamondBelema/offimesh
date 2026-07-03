"""Device management API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import NotFoundError
from app.middleware.auth import CurrentUser
from app.middleware.correlation_id import get_correlation_id
from app.models.device import Device
from app.schemas import DeviceRegisterRequest, ok_response
from app.repositories.device_repository import DeviceRepository
from app.repositories.audit_repository import AuditRepository
from app.models.audit import AuditLog

router = APIRouter(prefix="/v1/devices", tags=["Devices"])


@router.post("/register")
async def register_device(
    request: Request,
    body: DeviceRegisterRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Register a new device for the current user."""
    correlation_id = get_correlation_id(request)
    device_repo = DeviceRepository(db)
    audit_repo = AuditRepository(db)

    # Check if device already registered
    existing = await device_repo.get_by_fingerprint(body.device_fingerprint)
    if existing:
        from app.core.exceptions import ConflictError
        raise ConflictError("Device already registered", field="device_fingerprint")

    # Create device
    device = Device(
        user_id=user.id,
        device_fingerprint=body.device_fingerprint,
        device_public_key=body.device_public_key,
        attestation_token=body.attestation_token,
        device_name=body.device_name,
        device_type=body.device_type,
        trust_level="standard",
    )
    await device_repo.create(device)

    # Audit log
    await audit_repo.create(AuditLog(
        actor_type="user",
        actor_id=str(user.id),
        action="device.registered",
        resource="device",
        resource_id=str(device.id),
        correlation_id=correlation_id,
    ))

    return ok_response({
        "id": str(device.id),
        "device_name": device.device_name,
        "device_type": device.device_type,
        "trust_level": device.trust_level,
        "registered_at": device.registered_at.isoformat(),
    }, correlation_id)


@router.get("")
async def list_devices(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """List all devices for the current user."""
    correlation_id = get_correlation_id(request)
    device_repo = DeviceRepository(db)
    devices = await device_repo.get_by_user(user.id)

    return ok_response({
        "devices": [
            {
                "id": str(d.id),
                "device_name": d.device_name,
                "device_type": d.device_type,
                "trust_level": d.trust_level,
                "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
                "registered_at": d.registered_at.isoformat(),
            }
            for d in devices
        ],
        "total": len(devices),
    }, correlation_id)


@router.delete("/{device_id}")
async def revoke_device(
    device_id: str,
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Revoke a device."""
    correlation_id = get_correlation_id(request)
    device_repo = DeviceRepository(db)
    audit_repo = AuditRepository(db)

    import uuid
    revoked = await device_repo.revoke(uuid.UUID(device_id), user.id)

    if not revoked:
        raise NotFoundError("Device not found")

    await audit_repo.create(AuditLog(
        actor_type="user",
        actor_id=str(user.id),
        action="device.revoked",
        resource="device",
        resource_id=device_id,
        correlation_id=correlation_id,
    ))

    return ok_response({"revoked": True}, correlation_id)
