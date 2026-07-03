"""Centralized exception definitions."""
from __future__ import annotations

from typing import Any


class OffiMeshError(Exception):
    """Base exception for all OffiMesh errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.field = field
        self.details = details or {}


# --- Authentication Errors ---


class AuthenticationError(OffiMeshError):
    """Raised when authentication fails."""

    def __init__(
        self,
        message: str = "Authentication failed",
        code: str = "AUTHENTICATION_ERROR",
        field: str | None = None,
    ) -> None:
        super().__init__(message, code, status_code=401, field=field)


class InvalidTokenError(AuthenticationError):
    """Raised when JWT token is invalid or expired."""

    def __init__(self, message: str = "Invalid or expired token") -> None:
        super().__init__(message, code="INVALID_TOKEN")


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid."""

    def __init__(self, message: str = "Invalid credentials") -> None:
        super().__init__(message, code="INVALID_CREDENTIALS")


# --- Validation Errors ---


class ValidationError(OffiMeshError):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        code: str = "VALIDATION_ERROR",
    ) -> None:
        super().__init__(message, code, status_code=400, field=field)


class InvalidOTPError(ValidationError):
    """Raised when OTP is invalid."""

    def __init__(self, message: str = "Invalid OTP") -> None:
        super().__init__(message, field="otp", code="INVALID_OTP")


class InvalidPINError(ValidationError):
    """Raised when PIN is invalid."""

    def __init__(self, message: str = "Invalid PIN") -> None:
        super().__init__(message, field="pin", code="INVALID_PIN")


class PINRequiredError(ValidationError):
    """Raised when PIN is required but not provided."""

    def __init__(self) -> None:
        super().__init__("PIN required for this transaction", field="pin", code="PIN_REQUIRED")


# --- Resource Errors ---


class NotFoundError(OffiMeshError):
    """Raised when a resource is not found."""

    def __init__(self, resource: str = "Resource", resource_id: str | None = None) -> None:
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} with id '{resource_id}' not found"
        super().__init__(message, code="NOT_FOUND", status_code=404)


class ConflictError(OffiMeshError):
    """Raised when there's a conflict (e.g., duplicate entry)."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message, code="CONFLICT", status_code=409, field=field)


class UserAlreadyExistsError(ConflictError):
    """Raised when trying to create a user that already exists."""

    def __init__(self, field: str = "phone") -> None:
        super().__init__("User already registered", field=field)


class DeviceAlreadyRegisteredError(ConflictError):
    """Raised when trying to register an already registered device."""

    def __init__(self) -> None:
        super().__init__("Device already registered", field="device_fingerprint")


# --- Transaction Errors ---


class TransactionError(OffiMeshError):
    """Base for transaction-related errors."""

    def __init__(
        self,
        message: str,
        code: str = "TRANSACTION_ERROR",
        status_code: int = 400,
    ) -> None:
        super().__init__(message, code, status_code)


class InsufficientFundsError(TransactionError):
    """Raised when user has insufficient funds."""

    def __init__(self, required: int, available: int) -> None:
        super().__init__(
            f"Insufficient funds: required {required}, available {available}",
            code="INSUFFICIENT_FUNDS",
        )


class TokenExhaustedError(TransactionError):
    """Raised when offline token spending limit is reached."""

    def __init__(self) -> None:
        super().__init__(
            "Offline token spending limit exhausted",
            code="TOKEN_EXHAUSTED",
        )


class TokenExpiredError(TransactionError):
    """Raised when offline token has expired."""

    def __init__(self) -> None:
        super().__init__(
            "Offline token has expired",
            code="TOKEN_EXPIRED",
        )


class InvalidTokenStatusError(TransactionError):
    """Raised when token is in invalid state."""

    def __init__(self, status: str) -> None:
        super().__init__(
            f"Offline token is {status}",
            code="TOKEN_INVALID_STATUS",
        )


class ReplayAttackError(TransactionError):
    """Raised when a replay attack is detected."""

    def __init__(self) -> None:
        super().__init__(
            "Transaction nonce already used - possible replay attack",
            code="REPLAY_DETECTED",
            status_code=400,
        )


class SignatureVerificationError(TransactionError):
    """Raised when signature verification fails."""

    def __init__(self, detail: str = "Invalid signature") -> None:
        super().__init__(detail, code="SIGNATURE_INVALID")


class BatchLimitExceededError(TransactionError):
    """Raised when sync batch exceeds size limit."""

    def __init__(self, count: int, limit: int) -> None:
        super().__init__(
            f"Batch size {count} exceeds limit {limit}",
            code="BATCH_LIMIT_EXCEEDED",
        )


# --- Settlement Errors ---


class SettlementError(OffiMeshError):
    """Base for settlement-related errors."""

    def __init__(
        self,
        message: str,
        code: str = "SETTLEMENT_ERROR",
        status_code: int = 400,
    ) -> None:
        super().__init__(message, code, status_code)


class SettlementAlreadyProcessedException(SettlementError):
    """Raised when trying to settle an already settled transaction."""

    def __init__(self) -> None:
        super().__init__(
            "Transaction already settled",
            code="SETTLEMENT_ALREADY_PROCESSED",
        )


class SettlementPendingException(SettlementError):
    """Raised when settlement is still in progress."""

    def __init__(self) -> None:
        super().__init__(
            "Settlement is in progress",
            code="SETTLEMENT_PENDING",
            status_code=202,
        )


# --- Nomba Integration Errors ---


class NombaError(OffiMeshError):
    """Base for Nomba API errors."""

    def __init__(
        self,
        message: str,
        code: str = "NOMBA_ERROR",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code, status_code, details=details)


class NombaAuthError(NombaError):
    """Raised when Nomba authentication fails."""

    def __init__(self, detail: str = "Nomba authentication failed") -> None:
        super().__init__(detail, code="NOMBA_AUTH_ERROR", status_code=502)


class NombaTransferError(NombaError):
    """Raised when Nomba transfer fails."""

    def __init__(self, detail: str, nomba_code: str | None = None) -> None:
        super().__init__(
            detail,
            code="NOMBA_TRANSFER_ERROR",
            details={"nomba_code": nomba_code} if nomba_code else None,
        )


class NombaRateLimitError(NombaError):
    """Raised when Nomba rate limits our requests."""

    def __init__(self) -> None:
        super().__init__(
            "Nomba API rate limit exceeded",
            code="NOMBA_RATE_LIMITED",
            status_code=429,
        )


class NombaCircuitOpenError(NombaError):
    """Raised when circuit breaker is open."""

    def __init__(self) -> None:
        super().__init__(
            "Nomba service temporarily unavailable (circuit open)",
            code="NOMBA_CIRCUIT_OPEN",
            status_code=503,
        )


# --- Webhook Errors ---


class WebhookSignatureError(OffiMeshError):
    """Raised when webhook signature verification fails."""

    def __init__(self) -> None:
        super().__init__(
            "Invalid webhook signature",
            code="WEBHOOK_SIGNATURE_INVALID",
            status_code=401,
        )


class WebhookDuplicateError(OffiMeshError):
    """Raised when processing a duplicate webhook."""

    def __init__(self) -> None:
        super().__init__(
            "Webhook already processed",
            code="WEBHOOK_DUPLICATE",
            status_code=200,  # Return 200 to acknowledge
        )


# --- Permission Errors ---


class PermissionDeniedError(OffiMeshError):
    """Raised when user lacks permission for an action."""

    def __init__(self, action: str = "this action") -> None:
        super().__init__(
            f"Permission denied for {action}",
            code="PERMISSION_DENIED",
            status_code=403,
        )


class DeviceRevokedError(PermissionDeniedError):
    """Raised when device is revoked."""

    def __init__(self) -> None:
        super().__init__("Device has been revoked")
