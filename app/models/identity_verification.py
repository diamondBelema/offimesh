"""Identity verification model."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IdentityVerification(Base):
    """
    Identity verification records (NIN/BVN + face verification).

    In hackathon/test mode, this always succeeds.
    In production, integrates with Dojah/Smile Identity/VerifyMe.
    """
    __tablename__ = "identity_verifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_type: Mapped[str] = mapped_column(
        String(10),  # 'nin' or 'bvn'
        nullable=False,
        index=True,
    )
    id_number_encrypted: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
        index=True,
    )
    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    provider_reference: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    face_match_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    face_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        onupdate="now()",
        nullable=False,
    )

    __table_args__ = (
        Index("ix_identity_verifications_user_type", "user_id", "id_type"),
    )

    def __repr__(self) -> str:
        return f"<IdentityVerification {self.id_type} status={self.status}>"
