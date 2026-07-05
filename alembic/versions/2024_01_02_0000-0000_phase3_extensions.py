"""Phase 3 extensions: ledger, identity, fraud, device trust.

Revision ID: phase3_extensions
Revises: initial_schema
Create Date: 2024-01-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "phase3_extensions"
down_revision: Union[str, None] = "initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === Add columns to existing tables ===

    # Add trust-related columns to devices
    op.add_column("devices", sa.Column("device_fingerprint_hash", sa.String(128), nullable=True))
    op.add_column("devices", sa.Column("device_trust_score", sa.Integer, default=0))
    op.add_column("devices", sa.Column("is_hardware_backed_key", sa.Boolean, default=False))
    op.add_column("devices", sa.Column("play_integrity_last_verdict", sa.String(50), nullable=True))
    op.add_column("devices", sa.Column("play_integrity_last_check", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("play_integrity_fail_count", sa.Integer, default=0))
    op.add_column("devices", sa.Column("last_ip_address", sa.String(45), nullable=True))
    op.add_column("devices", sa.Column("last_gps_lat", sa.Float, nullable=True))
    op.add_column("devices", sa.Column("last_gps_lng", sa.Float, nullable=True))
    op.add_column("devices", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_devices_fingerprint_hash", "devices", ["device_fingerprint_hash"])

    # Add identity verification columns to users
    op.add_column("users", sa.Column("nin_verified", sa.Boolean, default=False))
    op.add_column("users", sa.Column("nin_verification_reference", sa.String(128), nullable=True))
    op.add_column("users", sa.Column("face_verified", sa.Boolean, default=False))
    op.add_column("users", sa.Column("face_verified_at", sa.DateTime(timezone=True), nullable=True))

    # Rename balance_kobo to available_balance_kobo for ledger system
    # Note: We keep balance_kobo for backward compatibility during migration
    op.add_column("users", sa.Column("available_balance_kobo", sa.BigInteger, default=0))
    op.add_column("users", sa.Column("locked_in_offline_tokens_kobo", sa.BigInteger, default=0))

    # === New Tables ===

    # Ledger balances table
    op.create_table(
        "ledger_balances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("available_balance_kobo", sa.BigInteger, default=0, nullable=False),
        sa.Column("locked_in_offline_tokens_kobo", sa.BigInteger, default=0, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ledger_balances_user_id", "ledger_balances", ["user_id"])

    # Ledger entries table (append-only)
    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("entry_type", sa.String(10), nullable=False),  # 'credit' or 'debit'
        sa.Column("amount_kobo", sa.BigInteger, nullable=False),
        sa.Column("reference_type", sa.String(50), nullable=False),
        sa.Column("reference_id", sa.String(128), nullable=True),
        sa.Column("balance_after_kobo", sa.BigInteger, nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )
    op.create_index("ix_ledger_entries_user_created", "ledger_entries", ["user_id", "created_at"])
    op.create_index("ix_ledger_entries_reference", "ledger_entries", ["reference_type", "reference_id"])

    # Identity verifications table
    op.create_table(
        "identity_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("id_type", sa.String(10), nullable=False),  # 'nin' or 'bvn'
        sa.Column("id_number_encrypted", sa.String(512), nullable=True),
        sa.Column("status", sa.String(30), default="pending", nullable=False, index=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("provider_reference", sa.String(128), nullable=True),
        sa.Column("face_match_score", sa.Float, nullable=True),
        sa.Column("face_verified", sa.Boolean, default=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_identity_verifications_user_type", "identity_verifications", ["user_id", "id_type"])

    # Fraud signals table
    op.create_table(
        "fraud_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("device_fingerprint_hash", sa.String(128), nullable=False, index=True),
        sa.Column("signal_type", sa.String(100), nullable=False, index=True),
        sa.Column("score_contribution", sa.Integer, nullable=False),
        sa.Column("checkpoint", sa.String(50), nullable=False),  # 'token_provisioning' or 'settlement_sync'
        sa.Column("context", postgresql.JSONB, nullable=True),
        sa.Column("action_taken", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )
    op.create_index("ix_fraud_signals_device_created", "fraud_signals", ["device_fingerprint_hash", "created_at"])

    # Device activity log table
    op.create_table(
        "device_activity_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("gps_lat", sa.Float, nullable=True),
        sa.Column("gps_lng", sa.Float, nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("play_integrity_verdict", sa.String(50), nullable=True),
        sa.Column("device_trust_score", sa.Integer, default=0),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )
    op.create_index("ix_device_activity_device_created", "device_activity_log", ["device_id", "created_at"])

    # Blacklisted devices table
    op.create_table(
        "blacklisted_devices",
        sa.Column("device_fingerprint_hash", sa.String(128), primary_key=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("auto_blacklisted", sa.Boolean, default=False),
        sa.Column("blacklisted_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Settlement claims table (for offline transactions)
    op.create_table(
        "settlement_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tx_id", sa.String(32), sa.ForeignKey("transactions.tx_id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("token_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("offline_tokens.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("settlement_serial", sa.String(64), unique=True, nullable=False),  # UNIQUE constraint for anti-double-spend
        sa.Column("customer_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("merchant_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("amount_kobo", sa.BigInteger, nullable=False),
        sa.Column("fraud_score", sa.Integer, default=0),
        sa.Column("flagged_reason", sa.String(255), nullable=True),
        sa.Column("status", sa.String(30), default="pending", nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_settlement_claims_serial", "settlement_claims", ["settlement_serial"], unique=True)

    # === Update offline_tokens for two-clock TTL ===
    # Add new columns for two-clock TTL system
    op.add_column("offline_tokens", sa.Column("serial", sa.String(26), unique=True, nullable=True))
    op.add_column("offline_tokens", sa.Column("nonce", sa.String(64), nullable=True))
    op.add_column("offline_tokens", sa.Column("device_fingerprint_hash", sa.String(128), nullable=True))
    op.add_column("offline_tokens", sa.Column("customer_spend_cutoff", sa.DateTime(timezone=True), nullable=True))
    op.add_column("offline_tokens", sa.Column("amount_kobo", sa.BigInteger, nullable=True))  # Rename from spending_limit

    # Rename spending_limit_kobo to amount_kobo if needed
    # Note: We add amount_kobo as new column and keep spending_limit_kobo for compatibility

    op.create_index("ix_offline_tokens_serial", "offline_tokens", ["serial"], unique=True)


def downgrade() -> None:
    # Drop new tables in reverse order
    op.drop_table("settlement_claims")
    op.drop_table("blacklisted_devices")
    op.drop_table("device_activity_log")
    op.drop_table("fraud_signals")
    op.drop_table("identity_verifications")
    op.drop_table("ledger_entries")
    op.drop_table("ledger_balances")

    # Drop columns from offline_tokens
    op.drop_column("offline_tokens", "amount_kobo")
    op.drop_column("offline_tokens", "customer_spend_cutoff")
    op.drop_column("offline_tokens", "device_fingerprint_hash")
    op.drop_column("offline_tokens", "nonce")
    op.drop_column("offline_tokens", "serial")
    op.drop_index("ix_offline_tokens_serial", "offline_tokens")

    # Drop columns from devices
    op.drop_column("devices", "last_used_at")
    op.drop_column("devices", "last_gps_lng")
    op.drop_column("devices", "last_gps_lat")
    op.drop_column("devices", "last_ip_address")
    op.drop_column("devices", "play_integrity_fail_count")
    op.drop_column("devices", "play_integrity_last_check")
    op.drop_column("devices", "play_integrity_last_verdict")
    op.drop_column("devices", "is_hardware_backed_key")
    op.drop_column("devices", "device_trust_score")
    op.drop_column("devices", "device_fingerprint_hash")
    op.drop_index("ix_devices_fingerprint_hash", "devices")

    # Drop columns from users
    op.drop_column("users", "locked_in_offline_tokens_kobo")
    op.drop_column("users", "available_balance_kobo")
    op.drop_column("users", "face_verified_at")
    op.drop_column("users", "face_verified")
    op.drop_column("users", "nin_verification_reference")
    op.drop_column("users", "nin_verified")
