"""Device trust service for security validation."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.blacklisted_device import BlacklistedDevice
from app.models.device import Device
from app.models.device_activity_log import DeviceActivityLog
from app.repositories.audit_repository import AuditRepository

logger = structlog.get_logger(__name__)

# Risk-based limits per specs
DEVICE_LIMITS = {
    "hardware_pass": {"max_token_kobo": 2000000, "ttl_hours": 72},  # ₦20,000, 72h
    "software_pass": {"max_token_kobo": 200000, "ttl_hours": 24},  # ₦2,000, 24h
    "blocked": {"max_token_kobo": 0, "ttl_hours": 0},
}


class DeviceTrustPayload:
    """Device trust payload from mobile app."""

    def __init__(
        self,
        device_fingerprint: str,
        play_integrity_token: str | None = None,
        gps_lat: float | None = None,
        gps_lng: float | None = None,
        device_model: str | None = None,
        os_version: str | None = None,
        is_hardware_backed_key: bool = False,
    ) -> None:
        self.device_fingerprint = device_fingerprint
        self.device_fingerprint_hash = hashlib.sha256(device_fingerprint.encode()).hexdigest()
        self.play_integrity_token = play_integrity_token
        self.gps_lat = gps_lat
        self.gps_lng = gps_lng
        self.device_model = device_model
        self.os_version = os_version
        self.is_hardware_backed_key = is_hardware_backed_key


class DeviceTrustService:
    """
    Service for validating device trust and security.

    Evaluates Play Integrity, hardware-backed keys, and activity patterns.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.audit_repo = AuditRepository(db)

    async def is_blacklisted(self, device_fingerprint_hash: str) -> bool:
        """Check if device is blacklisted."""
        result = await self.db.execute(
            select(BlacklistedDevice).where(
                BlacklistedDevice.device_fingerprint_hash == device_fingerprint_hash
            )
        )
        return result.scalar_one_or_none() is not None

    async def evaluate_trust(
        self,
        device: Device,
        trust_payload: DeviceTrustPayload,
        ip_address: str,
        action: str,
        correlation_id: str | None = None,
    ) -> dict:
        """
        Evaluate device trust and return trust level + limits.

        This is called on every sensitive action.
        """
        # Check if blacklisted first
        if await self.is_blacklisted(trust_payload.device_fingerprint_hash):
            logger.warning("device_blacklisted", fingerprint_hash=trust_payload.device_fingerprint_hash)
            return {
                "trusted": False,
                "trust_score": 0,
                "limits": DEVICE_LIMITS["blocked"],
                "reason": "Device is blacklisted",
            }

        # Verify Play Integrity (mocked for hackathon)
        play_integrity_result = await self._verify_play_integrity(
            trust_payload.play_integrity_token
        )

        # Calculate trust score
        trust_score = self._calculate_trust_score(
            device=device,
            play_integrity_result=play_integrity_result,
            trust_payload=trust_payload,
            ip_address=ip_address,
        )

        # Log activity
        await self._log_activity(
            device=device,
            trust_payload=trust_payload,
            ip_address=ip_address,
            action=action,
            play_integrity_verdict=play_integrity_result.get("verdict"),
            trust_score=trust_score,
            correlation_id=correlation_id,
        )

        # Update device record
        device.device_trust_score = trust_score
        device.last_ip_address = ip_address
        device.last_gps_lat = trust_payload.gps_lat
        device.last_gps_lng = trust_payload.gps_lng
        device.play_integrity_last_verdict = play_integrity_result.get("verdict")
        device.play_integrity_last_check = datetime.now(timezone.utc)
        device.is_hardware_backed_key = trust_payload.is_hardware_backed_key

        if play_integrity_result.get("passed"):
            device.play_integrity_fail_count = 0
        else:
            device.play_integrity_fail_count += 1

        await self.db.flush()

        # Determine limits based on device characteristics
        limits = self._get_limits(
            play_integrity_passed=play_integrity_result.get("passed", False),
            hardware_backed=trust_payload.is_hardware_backed_key,
            trust_score=trust_score,
        )

        return {
            "trusted": trust_score >= 40 and limits["max_token_kobo"] > 0,
            "trust_score": trust_score,
            "limits": limits,
            "play_integrity_passed": play_integrity_result.get("passed", False),
            "hardware_backed": trust_payload.is_hardware_backed_key,
        }

    async def _verify_play_integrity(self, token: str | None) -> dict:
        """
        Verify Google Play Integrity token.

        In production: Call Google Play Integrity API
        In hackathon: Always return PASS for valid-looking tokens

        TODO: Replace with live Google Play Integrity API call before production.
        """
        if not token:
            return {
                "passed": False,
                "verdict": "NO_TOKEN",
                "reason": "No Play Integrity token provided",
            }

        # HACKATHON MODE: Accept any token
        # In production, verify against:
        # https://play.googleapis.com/playintegrity/v1/packageNames/{packageName}/integrityTokens:decode

        logger.info(
            "play_integrity_check_mocked",
            token_prefix=token[:20] if token else None,
            # TODO: Replace with live Play Integrity verification
        )

        return {
            "passed": True,
            "verdict": "MEETS_DEVICE_INTEGRITY",
            "details": {
                "device_recognition": "MEETS_BASIC_INTEGRITY",
                "app_recognition": "PLAY_RECOGNIZED",
            },
        }

    def _calculate_trust_score(
        self,
        device: Device,
        play_integrity_result: dict,
        trust_payload: DeviceTrustPayload,
        ip_address: str,
    ) -> int:
        """
        Calculate device trust score (0-100).

        Based on:
        - Play Integrity verdict
        - Hardware-backed key
        - Device history
        - Activity patterns
        """
        score = 0

        # Play Integrity (most important)
        if play_integrity_result.get("passed"):
            if play_integrity_result.get("verdict") == "MEETS_DEVICE_INTEGRITY":
                score += 40
            elif play_integrity_result.get("verdict") == "MEETS_BASIC_INTEGRITY":
                score += 25
        else:
            # Failed integrity check is a major red flag
            score -= 30

        # Hardware-backed key
        if trust_payload.is_hardware_backed_key:
            score += 25

        # Device history (trusted device over time)
        if device.trust_level in ("standard", "elevated"):
            score += 15

        # Registration duration (older devices more trusted)
        if device.registered_at:
            days_registered = (datetime.now(timezone.utc) - device.registered_at).days
            if days_registered > 30:
                score += 10
            elif days_registered > 7:
                score += 5

        # Clamp to 0-100
        return max(0, min(100, score))

    def _get_limits(
        self,
        play_integrity_passed: bool,
        hardware_backed: bool,
        trust_score: int,
    ) -> dict:
        """Get risk-based limits for this device."""
        if trust_score < 40 or not play_integrity_passed:
            return DEVICE_LIMITS["blocked"]

        if hardware_backed and play_integrity_passed:
            return DEVICE_LIMITS["hardware_pass"]

        if play_integrity_passed:
            return DEVICE_LIMITS["software_pass"]

        return DEVICE_LIMITS["blocked"]

    async def _log_activity(
        self,
        device: Device,
        trust_payload: DeviceTrustPayload,
        ip_address: str,
        action: str,
        play_integrity_verdict: str | None,
        trust_score: int,
        correlation_id: str | None,
    ) -> None:
        """Log device activity for pattern analysis."""
        activity = DeviceActivityLog(
            device_id=device.id,
            user_id=device.user_id,
            ip_address=ip_address,
            gps_lat=trust_payload.gps_lat,
            gps_lng=trust_payload.gps_lng,
            action=action,
            play_integrity_verdict=play_integrity_verdict,
            device_trust_score=trust_score,
            metadata={
                "device_model": trust_payload.device_model,
                "os_version": trust_payload.os_version,
                "is_hardware_backed": trust_payload.is_hardware_backed_key,
            },
        )
        self.db.add(activity)

    async def check_impossible_travel(
        self,
        device: Device,
        new_lat: float | None,
        new_lng: float | None,
    ) -> bool:
        """
        Check for impossible travel patterns.

        Returns True if suspicious travel detected.
        """
        if not new_lat or not new_lng:
            return False

        if not device.last_gps_lat or not device.last_gps_lng:
            return False

        # Get last activity to check time
        result = await self.db.execute(
            select(DeviceActivityLog)
            .where(DeviceActivityLog.device_id == device.id)
            .order_by(DeviceActivityLog.created_at.desc())
            .limit(2)
        )
        activities = result.scalars().all()

        if len(activities) < 2:
            return False

        last_activity = activities[0]
        time_diff = (datetime.now(timezone.utc) - last_activity.created_at).total_seconds()

        if time_diff < 600:  # Less than 10 minutes
            # Calculate distance between coordinates (approximate)
            lat_diff = abs(new_lat - device.last_gps_lat)
            lng_diff = abs(new_lng - device.last_gps_lng)

            # Rough distance in km (using degrees to km approximation for Nigeria latitudes)
            distance_km = lat_diff * 111 + lng_diff * 111 * 0.87  # cos(30°) for Nigeria latitude

            # If more than 100km in 10 minutes, that's impossible
            if distance_km > 100:
                logger.warning(
                    "impossible_travel_detected",
                    device_id=str(device.id),
                    distance_km=distance_km,
                    time_seconds=time_diff,
                )
                return True

        return False

    async def blacklist_device(
        self,
        device_fingerprint_hash: str,
        reason: str,
        auto_blacklisted: bool = True,
        blacklisted_by: str | None = None,
        correlation_id: str | None = None,
    ) -> BlacklistedDevice:
        """Blacklist a device."""
        blacklisted = BlacklistedDevice(
            device_fingerprint_hash=device_fingerprint_hash,
            reason=reason,
            auto_blacklisted=auto_blacklisted,
            blacklisted_by=blacklisted_by or "system",
        )
        self.db.add(blacklisted)

        logger.warning(
            "device_blacklisted",
            fingerprint_hash=device_fingerprint_hash,
            reason=reason,
            auto=auto_blacklisted,
        )

        await self.audit_repo.create(AuditLog(
            actor_type="system",
            actor_id=blacklisted_by or "auto_blacklist",
            action="device.blacklisted",
            resource="device",
            resource_id=device_fingerprint_hash,
            metadata={"reason": reason, "auto": auto_blacklisted},
            correlation_id=correlation_id,
        ))

        await self.db.flush()
        return blacklisted
