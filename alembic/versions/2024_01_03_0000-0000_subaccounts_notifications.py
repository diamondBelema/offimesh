"""Sub-accounts, notifications, and Supabase tables.

Revision ID: subaccounts_notifications
Revises: phase3_extensions
Create Date: 2024-01-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "subaccounts_notifications"
down_revision: Union[str, None] = "phase3_extensions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === Nomba Sub-Accounts Tables ===

    # Nomba sub-account for treasury operations
    op.create_table(
        "nomba_sub_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("nomba_sub_account_id", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("account_ref", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("account_name", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(100), nullable=False, default="operational_treasury"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Sub-account balance snapshots for daily reconciliation
    op.create_table(
        "sub_account_balance_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sub_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("nomba_sub_accounts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("balance_kobo", sa.Integer, nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("ledger_total_kobo", sa.Integer, nullable=True),
        sa.Column("discrepancy_kobo", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_balance_snapshots_sub_account_captured", "sub_account_balance_snapshots", ["sub_account_id", "captured_at"])

    # === Notification Tables ===

    # User notifications
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("notification_type", sa.String(50), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("data", postgresql.JSONB, nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])

    # User notification preferences
    op.create_table(
        "notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("push_enabled", sa.Boolean, default=True),
        sa.Column("email_enabled", sa.Boolean, default=True),
        sa.Column("sms_enabled", sa.Boolean, default=False),
        sa.Column("transaction_notifications", sa.Boolean, default=True),
        sa.Column("security_notifications", sa.Boolean, default=True),
        sa.Column("promotional_notifications", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # === Add Supabase integration columns to users ===
    op.add_column("users", sa.Column("supabase_user_id", postgresql.UUID(as_uuid=True), nullable=True, unique=True, index=True))
    op.add_column("users", sa.Column("email", sa.String(255), nullable=True, unique=True, index=True))


def downgrade() -> None:
    # Drop notification tables
    op.drop_table("notification_preferences")
    op.drop_table("notifications")

    # Drop sub-account tables
    op.drop_table("sub_account_balance_snapshots")
    op.drop_table("nomba_sub_accounts")

    # Drop columns from users
    op.drop_column("users", "email")
    op.drop_column("users", "supabase_user_id")
