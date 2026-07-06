"""Add v2 offline token columns (serial, nonce, device_fingerprint_hash, customer_spend_cutoff, refunded_at, created_at) and rename spending_limit_kobo -> amount_kobo.

Revision ID: offline_tokens_v2
Revises: initial_schema
Create Date: 2026-07-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "offline_tokens_v2"
down_revision: Union[str, None] = "subaccounts_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Rename spending_limit_kobo -> amount_kobo
    op.alter_column(
        "offline_tokens",
        "spending_limit_kobo",
        new_column_name="amount_kobo",
    )

    # Step 2: Add new nullable columns
    op.add_column(
        "offline_tokens",
        sa.Column("serial", sa.String(32), nullable=True),
    )
    op.add_column(
        "offline_tokens",
        sa.Column("device_fingerprint_hash", sa.String(128), nullable=True),
    )
    op.add_column(
        "offline_tokens",
        sa.Column("nonce", sa.String(64), nullable=True),
    )
    op.add_column(
        "offline_tokens",
        sa.Column("customer_spend_cutoff", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "offline_tokens",
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "offline_tokens",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Step 3: Backfill data for existing rows
    # serial -> use token_id as fallback ULID-like value
    op.execute(
        "UPDATE offline_tokens SET serial = token_id WHERE serial IS NULL"
    )
    # device_fingerprint_hash -> empty string for existing rows
    op.execute(
        "UPDATE offline_tokens SET device_fingerprint_hash = '' WHERE device_fingerprint_hash IS NULL"
    )
    # nonce -> use id::text as fallback
    op.execute(
        "UPDATE offline_tokens SET nonce = id::text || '-nonce' WHERE nonce IS NULL"
    )
    # customer_spend_cutoff -> same as expires_at for existing rows
    op.execute(
        "UPDATE offline_tokens SET customer_spend_cutoff = expires_at WHERE customer_spend_cutoff IS NULL"
    )
    # created_at -> same as issued_at
    op.execute(
        "UPDATE offline_tokens SET created_at = issued_at WHERE created_at IS NULL"
    )

    # Step 4: Add NOT NULL and UNIQUE constraints
    op.alter_column("offline_tokens", "serial",
        existing_type=sa.String(32),
        nullable=False,
    )
    op.create_unique_constraint("uq_offline_tokens_serial", "offline_tokens", ["serial"])
    op.create_index("ix_tokens_serial_status", "offline_tokens", ["serial", "status"])

    op.alter_column("offline_tokens", "device_fingerprint_hash",
        existing_type=sa.String(128),
        nullable=False,
    )
    op.create_index("ix_tokens_device_fingerprint", "offline_tokens", ["device_fingerprint_hash"])

    op.alter_column("offline_tokens", "nonce",
        existing_type=sa.String(64),
        nullable=False,
    )
    op.create_unique_constraint("uq_offline_tokens_nonce", "offline_tokens", ["nonce"])

    op.alter_column("offline_tokens", "customer_spend_cutoff",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.create_index("ix_tokens_expires_status", "offline_tokens", ["expires_at", "status"])

    op.alter_column("offline_tokens", "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

    # Add status index if not exists (safe - IF NOT EXISTS isn't standard but PostgreSQL ignores duplicate index creation errors)
    op.create_index("ix_tokens_status", "offline_tokens", ["status"])


def downgrade() -> None:
    # Drop new indexes and constraints
    op.drop_index("ix_tokens_status", table_name="offline_tokens")
    op.drop_index("ix_tokens_expires_status", table_name="offline_tokens")
    op.drop_index("ix_tokens_device_fingerprint", table_name="offline_tokens")
    op.drop_index("ix_tokens_serial_status", table_name="offline_tokens")
    op.drop_constraint("uq_offline_tokens_nonce", "offline_tokens", type_="unique")
    op.drop_constraint("uq_offline_tokens_serial", "offline_tokens", type_="unique")

    # Remove new columns
    op.drop_column("offline_tokens", "created_at")
    op.drop_column("offline_tokens", "refunded_at")
    op.drop_column("offline_tokens", "customer_spend_cutoff")
    op.drop_column("offline_tokens", "nonce")
    op.drop_column("offline_tokens", "device_fingerprint_hash")
    op.drop_column("offline_tokens", "serial")

    # Rename amount_kobo back to spending_limit_kobo
    op.alter_column(
        "offline_tokens",
        "amount_kobo",
        new_column_name="spending_limit_kobo",
    )
