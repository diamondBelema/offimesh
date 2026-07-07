"""SMS service for sending OTPs and notifications via multiple providers."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


class SMSProvider(ABC):
    """Abstract base class for SMS providers."""
    
    @abstractmethod
    async def send(self, phone: str, message: str) -> dict:
        """Send SMS to phone number."""
        pass


class TermiiSMSProvider(SMSProvider):
    """Termii SMS provider (Nigerian-focused)."""

    def __init__(self) -> None:
        self.api_key = settings.sms_gateway_api_key
        self.sender_id = settings.sms_gateway_sender_id
        self.base_url = "https://api.termii.com/api"

    async def send(self, phone: str, message: str) -> dict:
        """Send SMS via Termii."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/sms/send",
                json={
                    "api_key": self.api_key,
                    "message": message,
                    "to": phone,
                    "from": self.sender_id,
                    "channel": "dnd",
                    "type": "plain",
                },
            )
            response.raise_for_status()
            return response.json()


class AfricaTalkingSMSProvider(SMSProvider):
    """Africa's Talking SMS provider. Popular across Africa, easy API.

    Requires SMS_GATEWAY_API_KEY (your AT apiKey) and
    SMS_GATEWAY_USERNAME (your AT username, default 'sandbox').
    Sign up at https://africastalking.com
    """

    def __init__(self) -> None:
        self.api_key = settings.sms_gateway_api_key
        self.username = getattr(settings, "sms_gateway_username", "sandbox")
        self.base_url = "https://api.africastalking.com/version1/messaging"

    async def send(self, phone: str, message: str) -> dict:
        """Send SMS via Africa's Talking."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.base_url,
                headers={
                    "apiKey": self.api_key,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={
                    "username": self.username,
                    "to": phone,
                    "message": message,
                },
            )
            response.raise_for_status()
            return response.json()


class MockSMSProvider(SMSProvider):
    """Mock SMS provider for development/testing."""
    
    async def send(self, phone: str, message: str) -> dict:
        """Log SMS instead of sending."""
        logger.info(
            "mock_sms_sent",
            phone=self._mask_phone(phone),
            message_length=len(message),
        )
        return {
            "status": "success",
            "message_id": f"mock_{phone}_{id(message)}",
            "provider": "mock",
        }
    
    def _mask_phone(self, phone: str) -> str:
        """Mask phone number for logging."""
        if len(phone) > 4:
            return phone[:3] + "***" + phone[-4:]
        return "***"


class SMSService:
    """SMS service with provider abstraction."""
    
    def __init__(self) -> None:
        self.provider = self._get_provider()
    
    def _get_provider(self) -> SMSProvider:
        """Get the configured SMS provider."""
        provider_type = getattr(settings, 'sms_provider', 'mock').lower()

        if provider_type == 'termii' and settings.sms_gateway_api_key:
            return TermiiSMSProvider()

        if provider_type == 'africastalking' and settings.sms_gateway_api_key:
            return AfricaTalkingSMSProvider()

        if provider_type == 'termii' or provider_type == 'africastalking':
            logger.warning(
                "sms_provider_fallback",
                provider=provider_type,
                reason="No SMS_GATEWAY_API_KEY configured",
            )
        return MockSMSProvider()
    
    async def send_otp(self, phone: str, otp: str) -> dict:
        """Send OTP via SMS."""
        message = f"Your OffiMesh verification code is: {otp}. This code expires in 10 minutes."
        return await self.send_sms(phone, message)
    
    async def send_sms(self, phone: str, message: str) -> dict:
        """Send SMS message."""
        try:
            result = await self.provider.send(phone, message)
            logger.info(
                "sms_sent",
                phone=self._mask_phone(phone),
                provider=self.provider.__class__.__name__,
            )
            return result
        except Exception as e:
            logger.error(
                "sms_send_failed",
                phone=self._mask_phone(phone),
                error=str(e),
            )
            raise
    
    async def send_transaction_notification(
        self,
        phone: str,
        message: str,
    ) -> dict:
        """Send transaction notification."""
        return await self.send_sms(phone, message)
    
    def _mask_phone(self, phone: str) -> str:
        """Mask phone number for logging."""
        if len(phone) > 4:
            return phone[:3] + "***" + phone[-4:]
        return "***"


def get_sms_service() -> SMSService:
    """Get SMS service instance."""
    return SMSService()
