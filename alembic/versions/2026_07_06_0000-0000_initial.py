"""Consolidated initial migration (idempotent - handles partial/empty DB).

Revision ID: 001_initial
Revises:
Create Date: 2026-07-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS users (
        id UUID DEFAULT gen_random_uuid() NOT NULL, phone_hash VARCHAR(128) NOT NULL,
        phone_salt VARCHAR(64) NOT NULL, phone_encrypted TEXT NOT NULL,
        name VARCHAR(255), email VARCHAR(255), pin_hash VARCHAR(255),
        bvn VARCHAR(255), bvn_verified BOOLEAN DEFAULT false,
        bvn_verification_reference VARCHAR(128),
        role VARCHAR(20) DEFAULT 'customer' NOT NULL,
        trust_level VARCHAR(20) DEFAULT 'untrusted' NOT NULL,
        status VARCHAR(20) DEFAULT 'pending_verification' NOT NULL,
        nomba_virtual_account_id VARCHAR(128),
        balance_kobo BIGINT DEFAULT 0 NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_phone_hash ON users (phone_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_status ON users (status)")

    op.execute("""CREATE TABLE IF NOT EXISTS devices (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
        device_fingerprint VARCHAR(128) NOT NULL,
        device_public_key TEXT NOT NULL, attestation_token TEXT,
        attestation_type VARCHAR(50),
        trust_level VARCHAR(20) DEFAULT 'untrusted' NOT NULL,
        device_name VARCHAR(255), device_type VARCHAR(50),
        device_fingerprint_hash VARCHAR(128),
        device_trust_score INTEGER DEFAULT 0,
        is_hardware_backed_key BOOLEAN DEFAULT false,
        play_integrity_last_verdict VARCHAR(50),
        play_integrity_last_check TIMESTAMPTZ,
        last_seen_at TIMESTAMPTZ,
        registered_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        revoked_at TIMESTAMPTZ, PRIMARY KEY (id))""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_devices_device_fingerprint ON devices (device_fingerprint)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_devices_user_trust ON devices (user_id, trust_level)")

    op.execute("""CREATE TABLE IF NOT EXISTS offline_tokens (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        token_id VARCHAR(64) NOT NULL, serial VARCHAR(32) NOT NULL,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
        device_id UUID REFERENCES devices(id) ON DELETE CASCADE NOT NULL,
        device_fingerprint_hash VARCHAR(128) NOT NULL,
        amount_kobo BIGINT NOT NULL, amount_used_kobo BIGINT DEFAULT 0 NOT NULL,
        nonce VARCHAR(64) NOT NULL, status VARCHAR(20) DEFAULT 'active' NOT NULL,
        server_signature TEXT NOT NULL,
        issued_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        customer_spend_cutoff TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        revoked_at TIMESTAMPTZ, revoked_reason VARCHAR(255),
        refunded_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_tokens_token_id ON offline_tokens (token_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_tokens_serial ON offline_tokens (serial)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_tokens_nonce ON offline_tokens (nonce)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tokens_user_id ON offline_tokens (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tokens_device_id ON offline_tokens (device_id)")

    op.execute("""CREATE TABLE IF NOT EXISTS transactions (
        tx_id VARCHAR(32) NOT NULL,
        payer_user_id UUID REFERENCES users(id) ON DELETE RESTRICT NOT NULL,
        payee_user_id UUID REFERENCES users(id) ON DELETE RESTRICT NOT NULL,
        amount_kobo BIGINT NOT NULL, currency VARCHAR(3) DEFAULT 'NGN' NOT NULL,
        offline_token_id UUID REFERENCES offline_tokens(id) ON DELETE SET NULL,
        merchant_reference VARCHAR(128), status VARCHAR(30) NOT NULL,
        nomba_reference VARCHAR(128), payer_signature TEXT NOT NULL,
        merchant_signature TEXT NOT NULL,
        signed_payload_hash VARCHAR(64) NOT NULL, fraud_score INTEGER DEFAULT 0,
        nonce VARCHAR(64) NOT NULL, sequence_number INTEGER NOT NULL,
        initiated_at TIMESTAMPTZ NOT NULL, synced_at TIMESTAMPTZ,
        settled_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (tx_id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tx_payer ON transactions (payer_user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tx_payee ON transactions (payee_user_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_tx_nonce ON transactions (nonce)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tx_payer_status ON transactions (payer_user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tx_payee_status ON transactions (payee_user_id, status)")

    op.execute("""CREATE TABLE IF NOT EXISTS transaction_events (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        tx_id VARCHAR(32) REFERENCES transactions(tx_id) ON DELETE CASCADE NOT NULL,
        event_type VARCHAR(50) NOT NULL, payload JSONB NOT NULL,
        device_id UUID, created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tx_events_tx ON transaction_events (tx_id)")

    op.execute("""CREATE TABLE IF NOT EXISTS settlements (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        tx_id VARCHAR(32) REFERENCES transactions(tx_id) ON DELETE RESTRICT NOT NULL,
        nomba_transfer_id VARCHAR(128), amount_kobo BIGINT NOT NULL,
        fee_kobo INTEGER DEFAULT 0, status VARCHAR(20) NOT NULL,
        attempts INTEGER DEFAULT 0, last_attempt_at TIMESTAMPTZ,
        settled_at TIMESTAMPTZ, error_code VARCHAR(50),
        error_message TEXT, bank_code VARCHAR(10),
        account_number VARCHAR(20), account_name VARCHAR(255),
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_settlements_tx ON settlements (tx_id)")

    op.execute("""CREATE TABLE IF NOT EXISTS virtual_accounts (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
        nomba_account_id VARCHAR(128) NOT NULL,
        account_ref VARCHAR(128) NOT NULL,
        nuban VARCHAR(10) NOT NULL, account_name VARCHAR(255) NOT NULL,
        bank_name VARCHAR(100) DEFAULT 'Nomba',
        expected_amount_kobo BIGINT, received_amount_kobo BIGINT,
        status VARCHAR(20) DEFAULT 'pending' NOT NULL,
        expires_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_va_account_ref ON virtual_accounts (account_ref)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_va_nuban ON virtual_accounts (nuban)")

    op.execute("""CREATE TABLE IF NOT EXISTS webhook_events (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        request_id VARCHAR(128) NOT NULL, event_type VARCHAR(50) NOT NULL,
        payload JSONB NOT NULL, raw_body TEXT,
        signature_valid BOOLEAN DEFAULT false,
        processed BOOLEAN DEFAULT false, processed_at TIMESTAMPTZ,
        processing_error TEXT,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_whe_request_id ON webhook_events (request_id)")

    op.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        actor_type VARCHAR(20) NOT NULL, actor_id VARCHAR(128),
        action VARCHAR(100) NOT NULL, resource VARCHAR(100),
        resource_id VARCHAR(128), metadata JSONB,
        ip_address VARCHAR(45), user_agent VARCHAR(255),
        correlation_id VARCHAR(64),
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")

    op.execute("""CREATE TABLE IF NOT EXISTS idempotency_keys (
        key VARCHAR(128) NOT NULL,
        request_hash VARCHAR(64) NOT NULL, response JSONB,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (key))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_idempotency_expires ON idempotency_keys (expires_at)")

    op.execute("""CREATE TABLE IF NOT EXISTS ledger_balances (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
        balance_kobo BIGINT DEFAULT 0 NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_lb_user ON ledger_balances (user_id)")

    op.execute("""CREATE TABLE IF NOT EXISTS ledger_entries (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        user_id UUID REFERENCES users(id) ON DELETE RESTRICT NOT NULL,
        entry_type VARCHAR(20) NOT NULL, amount_kobo BIGINT NOT NULL,
        reference_type VARCHAR(50) NOT NULL, reference_id VARCHAR(128),
        balance_after_kobo BIGINT NOT NULL, description TEXT,
        metadata JSONB,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_le_user_created ON ledger_entries (user_id, created_at)")

    op.execute("""CREATE TABLE IF NOT EXISTS identity_verifications (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
        verification_type VARCHAR(50) NOT NULL, status VARCHAR(20) NOT NULL,
        reference VARCHAR(128), provider_data JSONB,
        expires_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")

    op.execute("""CREATE TABLE IF NOT EXISTS fraud_signals (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
        signal_type VARCHAR(50) NOT NULL, severity VARCHAR(20) NOT NULL,
        description TEXT, metadata JSONB, expires_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")

    op.execute("""CREATE TABLE IF NOT EXISTS blacklisted_devices (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        device_fingerprint_hash VARCHAR(128) NOT NULL,
        reason TEXT NOT NULL, blacklisted_by UUID REFERENCES users(id),
        expires_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bd_fingerprint ON blacklisted_devices (device_fingerprint_hash)")

    op.execute("""CREATE TABLE IF NOT EXISTS device_activity_log (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        device_id UUID REFERENCES devices(id) ON DELETE CASCADE NOT NULL,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
        ip_address VARCHAR(45), gps_lat FLOAT, gps_lng FLOAT,
        action VARCHAR(100) NOT NULL,
        play_integrity_verdict VARCHAR(50),
        device_trust_score INTEGER, metadata JSONB,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dal_device_created ON device_activity_log (device_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dal_user_created ON device_activity_log (user_id, created_at)")

    op.execute("""CREATE TABLE IF NOT EXISTS nomba_sub_accounts (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        nomba_sub_account_id VARCHAR(128) NOT NULL,
        account_ref VARCHAR(128) NOT NULL,
        account_name VARCHAR(255) NOT NULL, bank VARCHAR(100),
        nuban VARCHAR(10), status VARCHAR(20) DEFAULT 'active' NOT NULL,
        balance_kobo BIGINT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_nsa_sub_id ON nomba_sub_accounts (nomba_sub_account_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_nsa_account_ref ON nomba_sub_accounts (account_ref)")

    op.execute("""CREATE TABLE IF NOT EXISTS sub_account_balance_snapshots (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        sub_account_id UUID REFERENCES nomba_sub_accounts(id) ON DELETE CASCADE NOT NULL,
        balance_kobo BIGINT NOT NULL, snapshot_date DATE NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")

    op.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
        type VARCHAR(50) NOT NULL, title VARCHAR(255) NOT NULL,
        body TEXT NOT NULL, data JSONB, read BOOLEAN DEFAULT false,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notif_user_created ON notifications (user_id, created_at)")

    op.execute("""CREATE TABLE IF NOT EXISTS notification_preferences (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
        notification_type VARCHAR(50) NOT NULL,
        channel VARCHAR(20) NOT NULL, enabled BOOLEAN DEFAULT true,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ix_np_user_type_channel
        ON notification_preferences (user_id, notification_type, channel)""")

    # --- Settlement claims table ---
    op.execute("""CREATE TABLE IF NOT EXISTS settlement_claims (
        id UUID DEFAULT gen_random_uuid() NOT NULL,
        settlement_id UUID REFERENCES settlements(id) ON DELETE CASCADE,
        offline_token_id UUID REFERENCES offline_tokens(id) ON DELETE SET NULL,
        serial VARCHAR(32) NOT NULL, tx_id VARCHAR(32) NOT NULL,
        amount_claimed_kobo BIGINT NOT NULL,
        status VARCHAR(20) DEFAULT 'pending' NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
        PRIMARY KEY (id))""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notification_preferences CASCADE")
    op.execute("DROP TABLE IF EXISTS notifications CASCADE")
    op.execute("DROP TABLE IF EXISTS sub_account_balance_snapshots CASCADE")
    op.execute("DROP TABLE IF EXISTS nomba_sub_accounts CASCADE")
    op.execute("DROP TABLE IF EXISTS device_activity_log CASCADE")
    op.execute("DROP TABLE IF EXISTS blacklisted_devices CASCADE")
    op.execute("DROP TABLE IF EXISTS fraud_signals CASCADE")
    op.execute("DROP TABLE IF EXISTS identity_verifications CASCADE")
    op.execute("DROP TABLE IF EXISTS ledger_entries CASCADE")
    op.execute("DROP TABLE IF EXISTS ledger_balances CASCADE")
    op.execute("DROP TABLE IF EXISTS idempotency_keys CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
    op.execute("DROP TABLE IF EXISTS webhook_events CASCADE")
    op.execute("DROP TABLE IF EXISTS virtual_accounts CASCADE")
    op.execute("DROP TABLE IF EXISTS settlement_claims CASCADE")
    op.execute("DROP TABLE IF EXISTS settlements CASCADE")
    op.execute("DROP TABLE IF EXISTS transaction_events CASCADE")
    op.execute("DROP TABLE IF EXISTS transactions CASCADE")
    op.execute("DROP TABLE IF EXISTS offline_tokens CASCADE")
    op.execute("DROP TABLE IF EXISTS devices CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
