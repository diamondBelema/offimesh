"""Blacklist worker for auto-blacklisting devices with fraud signals."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func

from app.core.database import get_session_context
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.blacklisted_device import BlacklistedDevice
from app.models.fraud_signal import FraudSignal
from app.repositories.audit_repository import AuditRepository
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

# Blacklist thresholds
THRESHOLD_SIGNAL_COUNT = 3  # 3+ signals in 7 days
THRESHOLD_DOUBLE_SPEND = 2  # 2+ double-spend attempts
THRESHOLD_INTEGRITY_FAIL = 3  # 3+ Play Integrity fails


@celery_app.task(
    name="app.workers.blacklist_worker.scan_for_blacklist_candidates",
    bind=True,
)
def scan_for_blacklist_candidates(self) -> dict:
    """
    Scan for devices that should be auto-blacklisted.

    Runs periodically (every 30 minutes) via Celery Beat.
    """
    import asyncio

    async def _scan():
        async with get_session_context() as db:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=7)

            # Find devices with 3+ fraud signals in last 7 days
            signal_count_query = (
                select(
                    FraudSignal.device_fingerprint_hash,
                    func.count(FraudSignal.id).label("signal_count"),
                )
                .where(FraudSignal.created_at >= cutoff)
                .group_by(FraudSignal.device_fingerprint_hash)
                .having(func.count(FraudSignal.id) >= THRESHOLD_SIGNAL_COUNT)
            )

            result = await db.execute(signal_count_query)
            high_signal_devices = result.all()

            # Find devices with multiple double-spend attempts
            double_spend_query = (
                select(
                    FraudSignal.device_fingerprint_hash,
                    func.count(FraudSignal.id).label("double_spend_count"),
                )
                .where(
                    FraudSignal.created_at >= cutoff,
                    FraudSignal.signal_type == "double_spend_attempt",
                )
                .group_by(FraudSignal.device_fingerprint_hash)
                .having(func.count(FraudSignal.id) >= THRESHOLD_DOUBLE_SPEND)
            )

            ds_result = await db.execute(double_spend_query)
            double_spend_devices = ds_result.all()

            # Find devices with repeated Play Integrity failures
            integrity_query = (
                select(
                    FraudSignal.device_fingerprint_hash,
                    func.count(FraudSignal.id).label("integrity_fail_count"),
                )
                .where(
                    FraudSignal.created_at >= cutoff,
                    FraudSignal.signal_type.in_(["play_integrity_fail", "play_integrity_no_token"]),
                )
                .group_by(FraudSignal.device_fingerprint_hash)
                .having(func.count(FraudSignal.id) >= THRESHOLD_INTEGRITY_FAIL)
            )

            int_result = await db.execute(integrity_query)
            integrity_fail_devices = int_result.all()

            # Combine all candidates
            device_hashes = set()
            for row in high_signal_devices:
                device_hashes.add(row.device_fingerprint_hash)
            for row in double_spend_devices:
                device_hashes.add(row.device_fingerprint_hash)
            for row in integrity_fail_devices:
                device_hashes.add(row.device_fingerprint_hash)

            logger.info(
                "blacklist_scan_complete",
                high_signal_count=len(high_signal_devices),
                double_spend_count=len(double_spend_devices),
                integrity_fail_count=len(integrity_fail_devices),
                total_candidates=len(device_hashes),
            )

            # Blacklist each candidate
            audit_repo = AuditRepository(db)
            blacklisted_count = 0

            for device_hash in device_hashes:
                # Check if already blacklisted
                existing = await db.execute(
                    select(BlacklistedDevice).where(
                        BlacklistedDevice.device_fingerprint_hash == device_hash
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                # Create blacklist entry
                reason = await _determine_blacklist_reason(db, device_hash)

                blacklisted = BlacklistedDevice(
                    device_fingerprint_hash=device_hash,
                    reason=reason,
                    auto_blacklisted=True,
                    blacklisted_by="blacklist_worker",
                )
                db.add(blacklisted)

                await audit_repo.create(AuditLog(
                    actor_type="system",
                    actor_id="blacklist_worker",
                    action="device.auto_blacklisted",
                    resource="device",
                    resource_id=device_hash,
                    metadata={"reason": reason, "source": "periodic_scan"},
                ))

                blacklisted_count += 1

            await db.commit()

            return {
                "scanned_devices": len(device_hashes),
                "blacklisted": blacklisted_count,
            }

    return asyncio.run(_scan())


async def _determine_blacklist_reason(db, device_hash: str) -> str:
    """Determine the reason for blacklisting."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    # Count signal types
    result = await db.execute(
        select(FraudSignal).where(
            FraudSignal.device_fingerprint_hash == device_hash,
            FraudSignal.created_at >= cutoff,
        )
    )
    signals = result.scalars().all()

    signal_types = [s.signal_type for s in signals]

    double_spend_count = signal_types.count("double_spend_attempt")
    integrity_fail_count = (
        signal_types.count("play_integrity_fail") +
        signal_types.count("play_integrity_no_token")
    )

    if double_spend_count >= THRESHOLD_DOUBLE_SPEND:
        return f"Auto-blacklisted: {double_spend_count} double-spend attempts in 7 days"
    elif integrity_fail_count >= THRESHOLD_INTEGRITY_FAIL:
        return f"Auto-blacklisted: {integrity_fail_count} Play Integrity failures in 7 days"
    else:
        return f"Auto-blacklisted: {len(signals)} fraud signals in 7 days"


@celery_app.task(
    name="app.workers.blacklist_worker.blacklist_device",
    bind=True,
    max_retries=3,
)
def blacklist_device(
    self,
    device_fingerprint_hash: str,
    reason: str,
    correlation_id: str | None = None,
) -> dict:
    """
    Blacklist a specific device.

    Triggered by fraud detection or admin action.
    """
    import asyncio

    async def _blacklist():
        async with get_session_context() as db:
            # Check if already blacklisted
            existing = await db.execute(
                select(BlacklistedDevice).where(
                    BlacklistedDevice.device_fingerprint_hash == device_fingerprint_hash
                )
            )
            if existing.scalar_one_or_none():
                logger.info("device_already_blacklisted", device_hash=device_fingerprint_hash[:16])
                return {"status": "already_blacklisted", "device_hash": device_fingerprint_hash}

            audit_repo = AuditRepository(db)

            blacklisted = BlacklistedDevice(
                device_fingerprint_hash=device_fingerprint_hash,
                reason=reason,
                auto_blacklisted=False,
                blacklisted_by="manual_blacklist",
            )
            db.add(blacklisted)

            await audit_repo.create(AuditLog(
                actor_type="system",
                actor_id="manual_blacklist",
                action="device.blacklisted",
                resource="device",
                resource_id=device_fingerprint_hash,
                metadata={"reason": reason},
                correlation_id=correlation_id,
            ))

            await db.commit()

            logger.warning(
                "device_blacklisted_manual",
                device_hash=device_fingerprint_hash[:16],
                reason=reason,
            )

            return {
                "status": "blacklisted",
                "device_hash": device_fingerprint_hash,
                "reason": reason,
            }

    try:
        return asyncio.run(_blacklist())
    except Exception as e:
        logger.error("manual_blacklist_failed", error=str(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.blacklist_worker.get_blacklist_stats",
    bind=True,
)
def get_blacklist_stats(self) -> dict:
    """
    Get statistics about blacklisted devices.
    """
    import asyncio

    async def _stats():
        async with get_session_context() as db:
            # Total blacklisted
            total_result = await db.execute(
                select(func.count(BlacklistedDevice.id))
            )
            total = total_result.scalar() or 0

            # Auto-blacklisted count
            auto_result = await db.execute(
                select(func.count(BlacklistedDevice.id)).where(
                    BlacklistedDevice.auto_blacklisted == True
                )
            )
            auto_count = auto_result.scalar() or 0

            # Recently blacklisted (last 24h)
            recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            recent_result = await db.execute(
                select(func.count(BlacklistedDevice.id)).where(
                    BlacklistedDevice.created_at >= recent_cutoff
                )
            )
            recent_count = recent_result.scalar() or 0

            return {
                "total_blacklisted": total,
                "auto_blacklisted": auto_count,
                "manual_blacklisted": total - auto_count,
                "blacklisted_last_24h": recent_count,
            }

    return asyncio.run(_stats())
