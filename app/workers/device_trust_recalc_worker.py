"""Device trust recalculation worker for periodic trust score updates."""
from __future__ import annotations

import structlog
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from app.core.database import get_session_context
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.device import Device
from app.models.device_activity_log import DeviceActivityLog
from app.repositories.audit_repository import AuditRepository
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="app.workers.device_trust_recalc_worker.recalculate_all_trust_scores",
    bind=True,
)
def recalculate_all_trust_scores(self) -> dict:
    """
    Recalculate trust scores for all active devices.

    Runs daily via Celery Beat.
    """
    import asyncio

    async def _recalc():
        async with get_session_context() as db:
            # Get all active devices (used in last 30 days)
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)

            result = await db.execute(
                select(Device).where(Device.last_used_at >= cutoff)
            )
            devices = result.scalars().all()

            logger.info("recalculating_trust_scores", device_count=len(devices))

            updated_count = 0

            for device in devices:
                try:
                    new_score = await _calculate_device_trust_score(db, device)

                    if new_score != device.device_trust_score:
                        old_score = device.device_trust_score
                        device.device_trust_score = new_score
                        updated_count += 1

                        logger.info(
                            "trust_score_updated",
                            device_id=str(device.id),
                            old_score=old_score,
                            new_score=new_score,
                        )

                except Exception as e:
                    logger.error(
                        "trust_recalc_failed",
                        device_id=str(device.id),
                        error=str(e),
                    )

            await db.commit()

            return {
                "total_devices": len(devices),
                "updated": updated_count,
            }

    return asyncio.run(_recalc())


async def _calculate_device_trust_score(db, device: Device) -> int:
    """
    Recalculate trust score for a device.

    Based on:
    - Play Integrity verdict history
    - Hardware-backed key status
    - Activity patterns
    - Device age
    """
    score = 0

    # Base score from Play Integrity history
    if device.play_integrity_last_verdict:
        if device.play_integrity_last_verdict == "MEETS_DEVICE_INTEGRITY":
            score += 40
        elif device.play_integrity_last_verdict == "MEETS_BASIC_INTEGRITY":
            score += 25

    # Check recent Play Integrity failure count
    if device.play_integrity_fail_count > 0:
        score -= min(device.play_integrity_fail_count * 10, 30)

    # Hardware-backed key bonus
    if device.is_hardware_backed_key:
        score += 25

    # Device trust level history
    if device.trust_level == "elevated":
        score += 20
    elif device.trust_level == "standard":
        score += 10

    # Registration age bonus
    if device.registered_at:
        days_registered = (datetime.now(timezone.utc) - device.registered_at).days
        if days_registered > 60:
            score += 15
        elif days_registered > 30:
            score += 10
        elif days_registered > 7:
            score += 5

    # Check recent activity patterns
    activity_score = await _calculate_activity_score(db, device)
    score += activity_score

    return max(0, min(100, score))


async def _calculate_activity_score(db, device: Device) -> int:
    """Calculate activity-based score component."""
    # Get last 30 days of activity
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    result = await db.execute(
        select(DeviceActivityLog)
        .where(
            DeviceActivityLog.device_id == device.id,
            DeviceActivityLog.created_at >= cutoff,
        )
        .order_by(DeviceActivityLog.created_at.desc())
        .limit(100)
    )
    activities = result.scalars().all()

    if not activities:
        return 0

    score = 0

    # Consistent usage pattern (good)
    if len(activities) >= 10:
        score += 5

    # Low fraud scores in activities (good)
    avg_trust = sum(a.device_trust_score or 0 for a in activities) / len(activities)
    if avg_trust >= 60:
        score += 5
    elif avg_trust < 30:
        score -= 10

    return score


@celery_app.task(
    name="app.workers.device_trust_recalc_worker.recalculate_device_trust",
    bind=True,
    max_retries=3,
)
def recalculate_device_trust(self, device_id: str) -> dict:
    """
    Recalculate trust score for a specific device.

    Triggered after significant events (failed integrity, suspicious activity).
    """
    import asyncio
    from uuid import UUID

    async def _recalc():
        async with get_session_context() as db:
            result = await db.execute(
                select(Device).where(Device.id == UUID(device_id))
            )
            device = result.scalar_one_or_none()

            if not device:
                raise ValueError(f"Device {device_id} not found")

            old_score = device.device_trust_score
            new_score = await _calculate_device_trust_score(db, device)

            device.device_trust_score = new_score

            audit_repo = AuditRepository(db)
            await audit_repo.create(AuditLog(
                actor_type="system",
                actor_id="trust_recalc_worker",
                action="device.trust_score_recalculated",
                resource="device",
                resource_id=device_id,
                metadata={"old_score": old_score, "new_score": new_score},
            ))

            await db.commit()

            return {
                "device_id": device_id,
                "old_score": old_score,
                "new_score": new_score,
                "trust_level": _determine_trust_level(new_score),
            }

    try:
        return asyncio.run(_recalc())
    except Exception as e:
        logger.error("device_trust_recalc_failed", device_id=device_id, error=str(e))
        raise self.retry(exc=e)


def _determine_trust_level(score: int) -> str:
    """Determine trust level from score."""
    if score >= 70:
        return "elevated"
    elif score >= 40:
        return "standard"
    else:
        return "limited"


@celery_app.task(
    name="app.workers.device_trust_recalc_worker.get_trust_score_distribution",
    bind=True,
)
def get_trust_score_distribution(self) -> dict:
    """
    Get distribution of trust scores across all devices.

    Useful for monitoring and alerting.
    """
    import asyncio

    async def _get():
        async with get_session_context() as db:
            from sqlalchemy import func

            # Get count by trust level
            elevated_count = await db.execute(
                select(func.count(Device.id)).where(Device.device_trust_score >= 70)
            )
            standard_count = await db.execute(
                select(func.count(Device.id)).where(
                    Device.device_trust_score >= 40,
                    Device.device_trust_score < 70,
                )
            )
            limited_count = await db.execute(
                select(func.count(Device.id)).where(Device.device_trust_score < 40)
            )

            return {
                "elevated": elevated_count.scalar() or 0,
                "standard": standard_count.scalar() or 0,
                "limited": limited_count.scalar() or 0,
            }

    return asyncio.run(_get())
