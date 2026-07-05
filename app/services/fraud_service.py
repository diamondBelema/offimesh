"""Fraud detection service for risk scoring at critical checkpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.blacklisted_device import BlacklistedDevice
from app.models.device import Device
from app.models.fraud_signal import FraudSignal
from app.models.user import User
from app.repositories.audit_repository import AuditRepository

logger = structlog.get_logger(__name__)

# Fraud signal types and their score contributions
SIGNAL_SCORES = {
    # Device trust signals
    "play_integrity_fail": 30,
    "play_integrity_no_token": 25,
    "device_rooted": 35,
    "emulator_detected": 40,
    "hardware_key_missing": 15,

    # Behavior signals
    "impossible_travel": 50,
    "rapid_device_switch": 20,
    "unusual_spend_pattern": 15,
    "multiple_failed_pins": 25,
    "off_hours_activity": 10,

    # Settlement signals
    "double_spend_attempt": 45,
    "token_replay": 50,
    "serial_mismatch": 35,
    "invalid_signature": 40,
    "amount_manipulation": 45,

    # Identity signals
    "face_mismatch": 30,
    "id_verification_failed": 25,
    "multiple_id_attempts": 20,
}

# Thresholds
BLOCK_THRESHOLD = 60  # Block token provisioning if score >= this
REVIEW_THRESHOLD = 60  # Flag for manual review at settlement if score >= this
AUTO_BLACKLIST_THRESHOLD = 3  # Auto-blacklist after N signals of same device in 7 days


class FraudService:
    """
    Fraud detection service for risk scoring.

    Runs synchronously at two critical checkpoints:
    - Checkpoint 1: Token provisioning (score >= 60 blocks)
    - Checkpoint 2: Settlement sync (score >= 60 flags for review)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.audit_repo = AuditRepository(db)

    async def evaluate_checkpoint_1(
        self,
        user_id: str,
        device_fingerprint_hash: str,
        trust_check_result: dict,
        correlation_id: str | None = None,
    ) -> dict:
        """
        Checkpoint 1: Token Provisioning.

        Returns fraud assessment. Score >= 60 blocks token issuance.
        """
        signals_to_record = []
        total_score = 0

        # Evaluate Play Integrity result
        if not trust_check_result.get("play_integrity_passed"):
            if trust_check_result.get("verdict") == "NO_TOKEN":
                signals_to_record.append("play_integrity_no_token")
            else:
                signals_to_record.append("play_integrity_fail")

        # Evaluate hardware-backed key
        if not trust_check_result.get("hardware_backed"):
            signals_to_record.append("hardware_key_missing")

        # Check for low trust score
        trust_score = trust_check_result.get("trust_score", 0)
        if trust_score < 40:
            signals_to_record.append("low_trust_score")

        # Calculate total score from signals
        for signal_type in signals_to_record:
            total_score += SIGNAL_SCORES.get(signal_type, 10)

        # Check historical signals for this device (last 7 days)
        historical_score = await self._get_historical_device_score(device_fingerprint_hash)
        total_score += historical_score

        # Record signals
        for signal_type in signals_to_record:
            await self._record_signal(
                user_id=user_id,
                device_fingerprint_hash=device_fingerprint_hash,
                signal_type=signal_type,
                checkpoint="token_provisioning",
                context={"trust_check": trust_check_result},
                correlation_id=correlation_id,
            )

        # Check for auto-blacklist trigger
        await self._check_auto_blacklist(device_fingerprint_hash, correlation_id)

        result = {
            "checkpoint": "token_provisioning",
            "fraud_score": total_score,
            "blocked": total_score >= BLOCK_THRESHOLD,
            "signals_detected": signals_to_record,
            "historical_score": historical_score,
        }

        logger.info(
            "fraud_checkpoint_1_complete",
            user_id=user_id,
            device_hash=device_fingerprint_hash[:16],
            fraud_score=total_score,
            blocked=result["blocked"],
            signals=len(signals_to_record),
        )

        return result

    async def evaluate_checkpoint_2(
        self,
        user_id: str,
        device_fingerprint_hash: str,
        settlement_data: dict,
        correlation_id: str | None = None,
    ) -> dict:
        """
        Checkpoint 2: Settlement Sync.

        Returns fraud assessment. Score >= 60 flags for manual review.
        """
        signals_to_record = []
        total_score = 0

        # Check for double-spend attempt
        if settlement_data.get("is_replay"):
            signals_to_record.append("token_replay")

        if settlement_data.get("serial_mismatch"):
            signals_to_record.append("serial_mismatch")

        if settlement_data.get("signature_invalid"):
            signals_to_record.append("invalid_signature")

        if settlement_data.get("amount_manipulation"):
            signals_to_record.append("amount_manipulation")

        if settlement_data.get("double_spend_attempt"):
            signals_to_record.append("double_spend_attempt")

        # Calculate total score
        for signal_type in signals_to_record:
            total_score += SIGNAL_SCORES.get(signal_type, 10)

        # Add historical score
        historical_score = await self._get_historical_device_score(device_fingerprint_hash)
        total_score += historical_score

        # Record signals
        for signal_type in signals_to_record:
            await self._record_signal(
                user_id=user_id,
                device_fingerprint_hash=device_fingerprint_hash,
                signal_type=signal_type,
                checkpoint="settlement_sync",
                context={"settlement_data": {k: str(v) for k, v in settlement_data.items()}},
                correlation_id=correlation_id,
            )

        # Check for auto-blacklist trigger
        await self._check_auto_blacklist(device_fingerprint_hash, correlation_id)

        result = {
            "checkpoint": "settlement_sync",
            "fraud_score": total_score,
            "flagged_for_review": total_score >= REVIEW_THRESHOLD,
            "signals_detected": signals_to_record,
            "historical_score": historical_score,
        }

        logger.info(
            "fraud_checkpoint_2_complete",
            user_id=user_id,
            device_hash=device_fingerprint_hash[:16],
            fraud_score=total_score,
            flagged=result["flagged_for_review"],
            signals=len(signals_to_record),
        )

        return result

    async def record_signal(
        self,
        user_id: str,
        device_fingerprint_hash: str,
        signal_type: str,
        checkpoint: str,
        context: dict | None = None,
        correlation_id: str | None = None,
    ) -> FraudSignal:
        """Record a fraud signal manually (for ad-hoc signal injection)."""
        return await self._record_signal(
            user_id=user_id,
            device_fingerprint_hash=device_fingerprint_hash,
            signal_type=signal_type,
            checkpoint=checkpoint,
            context=context,
            correlation_id=correlation_id,
        )

    async def _record_signal(
        self,
        user_id: str,
        device_fingerprint_hash: str,
        signal_type: str,
        checkpoint: str,
        context: dict | None = None,
        correlation_id: str | None = None,
    ) -> FraudSignal:
        """Internal: record a fraud signal to the database."""
        score_contribution = SIGNAL_SCORES.get(signal_type, 10)

        signal = FraudSignal(
            user_id=uuid.UUID(user_id),
            device_fingerprint_hash=device_fingerprint_hash,
            signal_type=signal_type,
            score_contribution=score_contribution,
            checkpoint=checkpoint,
            context=context,
        )
        self.db.add(signal)
        await self.db.flush()

        logger.info(
            "fraud_signal_recorded",
            signal_id=str(signal.id),
            user_id=user_id,
            signal_type=signal_type,
            score=score_contribution,
            checkpoint=checkpoint,
        )

        # Audit log for significant signals
        if score_contribution >= 30:
            await self.audit_repo.create(AuditLog(
                actor_type="system",
                actor_id="fraud_detection",
                action=f"fraud.signal_{signal_type}",
                resource="fraud_signal",
                resource_id=str(signal.id),
                metadata={"score": score_contribution, "checkpoint": checkpoint},
                correlation_id=correlation_id,
            ))

        return signal

    async def _get_historical_device_score(
        self,
        device_fingerprint_hash: str,
        days: int = 7,
    ) -> int:
        """Get accumulated score from signals in the last N days for this device."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.db.execute(
            select(func.sum(FraudSignal.score_contribution)).where(
                FraudSignal.device_fingerprint_hash == device_fingerprint_hash,
                FraudSignal.created_at >= cutoff,
            )
        )
        total = result.scalar()
        return total or 0

    async def _check_auto_blacklist(
        self,
        device_fingerprint_hash: str,
        correlation_id: str | None = None,
    ) -> bool:
        """
        Check if device should be auto-blacklisted.

        Triggers if device has 3+ signals in last 7 days OR
        2+ double-spend attempts OR 3+ Play Integrity fails.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        # Count all signals for this device
        result = await self.db.execute(
            select(FraudSignal).where(
                FraudSignal.device_fingerprint_hash == device_fingerprint_hash,
                FraudSignal.created_at >= cutoff,
            )
        )
        signals = result.scalars().all()

        # Check if already blacklisted
        blacklist_check = await self.db.execute(
            select(BlacklistedDevice).where(
                BlacklistedDevice.device_fingerprint_hash == device_fingerprint_hash
            )
        )
        if blacklist_check.scalar_one_or_none():
            return False  # Already blacklisted

        # Count signal types
        signal_types = [s.signal_type for s in signals]

        double_spend_count = signal_types.count("double_spend_attempt")
        integrity_fail_count = (
            signal_types.count("play_integrity_fail") +
            signal_types.count("play_integrity_no_token")
        )

        should_blacklist = False
        reason = ""

        if len(signals) >= AUTO_BLACKLIST_THRESHOLD:
            should_blacklist = True
            reason = f"Auto-blacklisted: {len(signals)} fraud signals in 7 days"
        elif double_spend_count >= 2:
            should_blacklist = True
            reason = f"Auto-blacklisted: {double_spend_count} double-spend attempts"
        elif integrity_fail_count >= 3:
            should_blacklist = True
            reason = f"Auto-blacklisted: {integrity_fail_count} Play Integrity failures"

        if should_blacklist:
            blacklisted = BlacklistedDevice(
                device_fingerprint_hash=device_fingerprint_hash,
                reason=reason,
                auto_blacklisted=True,
                blacklisted_by="fraud_detection",
            )
            self.db.add(blacklisted)

            logger.warning(
                "device_auto_blacklisted",
                device_hash=device_fingerprint_hash[:16],
                reason=reason,
                signal_count=len(signals),
            )

            await self.audit_repo.create(AuditLog(
                actor_type="system",
                actor_id="fraud_detection_auto_blacklist",
                action="device.auto_blacklisted",
                resource="device",
                resource_id=device_fingerprint_hash,
                metadata={"reason": reason, "signal_count": len(signals)},
                correlation_id=correlation_id,
            ))

            await self.db.flush()

        return should_blacklist

    async def get_user_risk_profile(self, user_id: str) -> dict:
        """Get accumulated risk profile for a user."""
        result = await self.db.execute(
            select(FraudSignal).where(
                FraudSignal.user_id == uuid.UUID(user_id)
            ).order_by(FraudSignal.created_at.desc())
        )
        signals = result.scalars().all()

        total_score = sum(s.score_contribution for s in signals)

        return {
            "user_id": user_id,
            "total_fraud_score": total_score,
            "signal_count": len(signals),
            "signals_by_type": self._group_signals_by_type(signals),
            "recent_signals": [
                {
                    "type": s.signal_type,
                    "score": s.score_contribution,
                    "checkpoint": s.checkpoint,
                    "created_at": s.created_at.isoformat(),
                }
                for s in signals[:10]
            ],
        }

    def _group_signals_by_type(self, signals: list[FraudSignal]) -> dict:
        """Group signals by type with counts."""
        counts: dict[str, int] = {}
        for signal in signals:
            counts[signal.signal_type] = counts.get(signal.signal_type, 0) + 1
        return counts
