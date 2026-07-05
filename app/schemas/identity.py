"""Identity verification Pydantic schemas."""
from __future__ import annotations

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


# --- Request Schemas ---


class InitiateVerificationRequest(BaseSchema):
    """Request to initiate identity verification (NIN/BVN)."""

    id_type: str = Field(description="ID type: 'nin' or 'bvn'")
    id_number: str = Field(min_length=10, max_length=20, description="NIN or BVN number")

    @field_validator("id_type")
    @classmethod
    def validate_id_type(cls, v: str) -> str:
        if v not in ("nin", "bvn"):
            raise ValueError("id_type must be 'nin' or 'bvn'")
        return v


class VerifyFaceRequest(BaseSchema):
    """Request to verify face against ID photo."""

    id_type: str = Field(description="ID type: 'nin' or 'bvn'")
    selfie_image_base64: str = Field(description="Base64-encoded selfie image")

    @field_validator("id_type")
    @classmethod
    def validate_id_type(cls, v: str) -> str:
        if v not in ("nin", "bvn"):
            raise ValueError("id_type must be 'nin' or 'bvn'")
        return v


# --- Response Schemas ---


class VerificationStatusResponse(BaseSchema):
    """Identity verification status."""

    nin_verified: bool
    bvn_verified: bool
    face_verified: bool
    can_provision_offline_token: bool


class VerificationDetail(BaseSchema):
    """Detailed verification info for a specific ID type."""

    status: str
    verified_at: str | None
    face_match_score: float | None


class InitiateVerificationResponse(BaseSchema):
    """Response after initiating verification."""

    verification_id: str
    id_type: str
    status: str
    message: str = "Verification initiated"


class VerifyFaceResponse(BaseSchema):
    """Response after face verification."""

    verification_id: str
    id_type: str
    status: str
    face_match_score: float
    face_verified: bool
    message: str


class CanProvisionTokenResponse(BaseSchema):
    """Response for token provisioning eligibility check."""

    can_provision: bool
    reason: str
    requirements: list[str]


# --- Device Trust Schemas ---


class DeviceTrustPayloadSchema(BaseSchema):
    """Device trust payload for token provisioning."""

    device_fingerprint: str = Field(description="Unique device fingerprint")
    play_integrity_token: str | None = Field(default=None, description="Google Play Integrity token")
    gps_lat: float | None = Field(default=None, ge=-90, le=90)
    gps_lng: float | None = Field(default=None, ge=-180, le=180)
    device_model: str | None = Field(default=None, max_length=100)
    os_version: str | None = Field(default=None, max_length=50)
    is_hardware_backed_key: bool = Field(default=False)


class TrustEvaluationResponse(BaseSchema):
    """Device trust evaluation result."""

    trusted: bool
    trust_score: int
    limits: dict
    play_integrity_passed: bool
    hardware_backed: bool


# --- Fraud Schemas ---


class FraudAssessmentResponse(BaseSchema):
    """Fraud assessment result."""

    checkpoint: str
    fraud_score: int
    blocked: bool = False
    flagged_for_review: bool = False
    signals_detected: list[str]
