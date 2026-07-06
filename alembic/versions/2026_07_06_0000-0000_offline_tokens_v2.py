"""Create offline_tokens with complete v2 schema.

This migration handles both cases:
- Table doesn't exist yet (create with full v2 schema)
- Table exists with v1 schema (add v2 columns, rename spending_limit_kobo)

Revision ID: offline_tokens_v2
Revises: subaccounts_notifications
Create Date: 2026-07-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision: str = "offline_tokens_v2"
down_revision: Union[str, None] = "subaccounts_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "offline_tokens" not in tables:
        # Create table from scratch with v2 schema
        op.create_table(
            "offline_tokens",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("token_id", sa.String(64), unique=True, nullable=False, index=True),
            sa.Column("serial", sa.String(32), unique=True, nullable=False, index=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("device_fingerprint_hash", sa.String(128), nullable=False, index=True),
            sa.Column("amount_kobo", sa.BigInteger, nullable=False),
            sa.Column("amount_used_kobo", sa.BigInteger, default=0, nullable=False),
            sa.Column("nonce", sa.String(64), unique=True, nullable=False),
            sa.Column("status", sa.String(20), default="active", nullable=False, index=True),
            sa.Column("server_signature", sa.Text, nullable=False),
            sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("customer_spend_cutoff", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_reason", sa.String(255), nullable=True),
            sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_tokens_token_id_status", "offline_tokens", ["token_id", "status"])
        op.create_index("ix_tokens_user_status", "offline_tokens", ["user_id", "status"])
        op.create_index("ix_tokens_serial_status", "offline_tokens", ["serial", "status"])
        op.create_index("ix_tokens_expires_status", "offline_tokens", ["expires_at", "status"])
    else:
        # Table exists with v1 schema - migrate
        op.alter_column(
            "offline_tokens",
            "spending_limit_kobo",
            new_column_name="amount_kobo",
        )
        op.add_column("offline_tokens", sa.Column("serial", sa.String(32), nullable=True))
        op.add_column("offline_tokens", sa.Column("device_fingerprint_hash", sa.String(128), nullable=True))
        op.add_column("offline_tokens", sa.Column("nonce", sa.String(64), nullable=True))
        op.add_column("offline_tokens", sa.Column("customer_spend_cutoff", sa.DateTime(timezone=True), nullable=True))
        op.add_column("offline_tokens", sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column("offline_tokens", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))

        op.execute("UPDATE offline_tokens SET serial = token_id WHERE serial IS NULL")
        op.execute("UPDATE offline_tokens SET device_fingerprint_hash = '' WHERE device_fingerprint_hash IS NULL")
        op.execute("UPDATE offline_tokens SET nonce = id::text || '-nonce' WHERE nonce IS NULL")
        op.execute("UPDATE offline_tokens SET customer_spend_cutoff = expires_at WHERE customer_spend_cutoff IS NULL")
        op.execute("UPDATE offline_tokens SET created_at = issued_at WHERE created_at IS NULL")

        op.alter_column("offline_tokens", "serial", existing_type=sa.String(32), nullable=False)
        op.create_unique_constraint("uq_offline_tokens_serial", "offline_tokens", ["serial"])
        op.create_index("ix_tokens_serial_status", "offline_tokens", ["serial", "status"])
        op.alter_column("offline_tokens", "device_fingerprint_hash", existing_type=sa.String(128), nullable=False)
        op.create_index("ix_tokens_device_fingerprint", "offline_tokens", ["device_fingerprint_hash"])
        op.alter_column("offline_tokens", "nonce", existing_type=sa.String(64), nullable=False)
        op.create_unique_constraint("uq_offline_tokens_nonce", "offline_tokens", ["nonce"])
        op.alter_column("offline_tokens", "customer_spend_cutoff", existing_type=sa.DateTime(timezone=True), nullable=False)
        op.create_index("ix_tokens_expires_status", "offline_tokens", ["expires_at", "status"])
        op.alter_column("offline_tokens", "created_at", existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    raise RuntimeError("Downgrade not supported for this complex migration - restore from backup instead")
