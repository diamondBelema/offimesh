"""Initial schema creation.

Revision ID: initial_schema
Revises:
Create Date: 2024-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone_hash", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("phone_salt", sa.String(64), nullable=False),
        sa.Column("phone_encrypted", sa.Text, nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True, unique=True),
        sa.Column("pin_hash", sa.String(255), nullable=True),
        sa.Column("bvn", sa.String(255), nullable=True),
        sa.Column("bvn_verified", sa.Boolean, default=False),
        sa.Column("bvn_verification_reference", sa.String(128), nullable=True),
        sa.Column("role", sa.String(20), default="customer", nullable=False),
        sa.Column("trust_level", sa.String(20), default="untrusted", nullable=False),
        sa.Column("status", sa.String(20), default="pending_verification", nullable=False),
        sa.Column("nomba_virtual_account_id", sa.String(128), nullable=True),
        sa.Column("balance_kobo", sa.BigInteger, default=0, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_phone_hash", "users", ["phone_hash"])
    op.create_index("ix_users_status", "users", ["status"])

    # Devices table
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("device_fingerprint", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("device_public_key", sa.Text, nullable=False),
        sa.Column("attestation_token", sa.Text, nullable=True),
        sa.Column("attestation_type", sa.String(50), nullable=True),
        sa.Column("trust_level", sa.String(20), default="untrusted", nullable=False),
        sa.Column("device_name", sa.String(255), nullable=True),
        sa.Column("device_type", sa.String(50), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_devices_user_trust", "devices", ["user_id", "trust_level"])

    # Offline tokens table
    op.create_table(
        "offline_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("token_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("spending_limit_kobo", sa.BigInteger, nullable=False),
        sa.Column("amount_used_kobo", sa.BigInteger, default=0, nullable=False),
        sa.Column("status", sa.String(20), default="active", nullable=False),
        sa.Column("server_signature", sa.Text, nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(255), nullable=True),
    )
    op.create_index("ix_tokens_token_id_status", "offline_tokens", ["token_id", "status"])
    op.create_index("ix_tokens_user_status", "offline_tokens", ["user_id", "status"])

    # Transactions table
    op.create_table(
        "transactions",
        sa.Column("tx_id", sa.String(32), primary_key=True),
        sa.Column("payer_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("payee_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("amount_kobo", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.String(3), default="NGN", nullable=False),
        sa.Column("offline_token_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("offline_tokens.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("merchant_reference", sa.String(128), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("nomba_reference", sa.String(128), nullable=True, index=True),
        sa.Column("payer_signature", sa.Text, nullable=False),
        sa.Column("merchant_signature", sa.Text, nullable=False),
        sa.Column("signed_payload_hash", sa.String(64), nullable=False),
        sa.Column("fraud_score", sa.Integer, default=0),
        sa.Column("nonce", sa.String(64), nullable=False, unique=True),
        sa.Column("sequence_number", sa.Integer, nullable=False),
        sa.Column("initiated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_transactions_status_created", "transactions", ["status", "created_at"])
    op.create_index("ix_transactions_payer_status", "transactions", ["payer_user_id", "status"])
    op.create_index("ix_transactions_payee_status", "transactions", ["payee_user_id", "status"])

    # Transaction events table
    op.create_table(
        "transaction_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tx_id", sa.String(32), sa.ForeignKey("transactions.tx_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tx_events_tx_id_created", "transaction_events", ["tx_id", "created_at"])

    # Settlements table
    op.create_table(
        "settlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tx_id", sa.String(32), sa.ForeignKey("transactions.tx_id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("nomba_transfer_id", sa.String(128), unique=True, nullable=True),
        sa.Column("amount_kobo", sa.BigInteger, nullable=False),
        sa.Column("fee_kobo", sa.Integer, default=0),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("attempts", sa.Integer, default=0),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("bank_code", sa.String(10), nullable=True),
        sa.Column("account_number", sa.String(20), nullable=True),
        sa.Column("account_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Virtual accounts table
    op.create_table(
        "virtual_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("nomba_account_id", sa.String(128), nullable=False, index=True),
        sa.Column("account_ref", sa.String(128), unique=True, nullable=False),
        sa.Column("nuban", sa.String(10), nullable=False, index=True),
        sa.Column("account_name", sa.String(255), nullable=False),
        sa.Column("bank_name", sa.String(100), default="Nomba", nullable=False),
        sa.Column("expected_amount_kobo", sa.BigInteger, nullable=True),
        sa.Column("received_amount_kobo", sa.BigInteger, nullable=True),
        sa.Column("status", sa.String(20), default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_virtual_accounts_user_status", "virtual_accounts", ["user_id", "status"])

    # Webhook events table
    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_id", sa.String(128), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False, index=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("raw_body", sa.Text, nullable=True),
        sa.Column("signature_valid", sa.Boolean, default=False),
        sa.Column("processed", sa.Boolean, default=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_webhook_events_request_id", "webhook_events", ["request_id"])

    # Audit log table
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=True),
        sa.Column("action", sa.String(100), nullable=False, index=True),
        sa.Column("resource", sa.String(100), nullable=True, index=True),
        sa.Column("resource_id", sa.String(128), nullable=True, index=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )

    # Idempotency keys table
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )
    op.create_index("ix_idempotency_expires", "idempotency_keys", ["expires_at"])


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("audit_log")
    op.drop_table("webhook_events")
    op.drop_table("virtual_accounts")
    op.drop_table("settlements")
    op.drop_table("transaction_events")
    op.drop_table("transactions")
    op.drop_table("offline_tokens")
    op.drop_table("devices")
    op.drop_table("users")
