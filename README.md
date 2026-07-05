# OffiMesh - Offline-First Payment Infrastructure for Africa

**Production-grade FastAPI backend for offline-first payments, settling through the Nomba payment API.**

---

## Overview

OffiMesh is designed to extend Nomba's payment network into environments without reliable internet connectivity. It enables customers to make payments to merchants offline, with transactions syncing and settling when connectivity is restored.

### Core Innovation

In many parts of Africa, internet connectivity is unreliable, creating a barrier for digital payments. OffiMesh solves this by:

1. **Pre-authorizing offline spending** via cryptographically-signed tokens
2. **Recording transactions locally** with Ed25519 signatures from both parties
3. **Syncing transactions in batches** when connectivity is available
4. **Settling via Nomba API** with proper bank transfer lookups
5. **Reconciling nightly** to catch any discrepancies

---

## Key Features

### Offline Token Economy with Two-Clock TTL

- **Two-clock TTL system**: Separate customer spend cutoff (48h) and token expiry (72h)
- **Risk-based limits**: Hardware-backed devices get ₦20,000/72h; software-only get ₦2,000/24h
- **Atomic spending**: Row-level locking prevents over-spending
- **Automatic refunds**: Unused balance returned when tokens expire

### Identity Verification (KYC)

- **NIN/BVN verification**: Integration with Nigerian identity systems
- **Face verification**: Selfie-to-ID-photo matching
- **Gating**: Users must complete NIN + face verification before provisioning offline tokens

### Fraud Detection at Two Checkpoints

- **Checkpoint 1 (Token Provisioning)**: Fraud score ≥60 blocks token issuance
- **Checkpoint 2 (Settlement Sync)**: Fraud score ≥60 flags for manual review
- **Auto-blacklisting**: 3+ signals, 2+ double-spend attempts, or 3+ Play Integrity failures

### Device Trust & Security

- **Google Play Integrity API** verification
- **Hardware-backed key** detection for elevated trust
- **Impossible travel detection** using GPS coordinates
- **Device blacklist middleware** blocks requests from flagged devices

### Double-Entry Ledger

All money movements tracked via immutable double-entry bookkeeping:
- `ledger_balances`: Current user balances
- `ledger_entries`: Append-only transaction log
- Balance integrity verification API

### Nomba Sub-Account Treasury

- Single operational treasury sub-account for internal bookkeeping
- Daily balance snapshots for reconciliation
- **IMPORTANT**: Virtual accounts never scoped to sub-account due to known Nomba limitation

### Supabase Integration

- **Authentication**: Email/password via Supabase Auth
- **Real-time notifications**: Push alerts via Supabase Realtime
- **JWT verification**: Seamless integration with Supabase tokens

---

## Architecture

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          MOBILE CLIENT LAYER                             │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐  │
│  │   Customer App     │  │   Merchant App     │  │   Admin Dashboard  │  │
│  │   (Offline-capable)│  │   (Offline-capable)│  │                    │  │
│  │                    │  │                    │  │                    │  │
│  │ • Local Ledger     │  │ • QR Scanner       │  │ • User Management  │  │
│  │ • QR Generator     │  │ • Payment Receipt  │  │ • Transaction View  │  │
│  │ • Ed25519 Keys     │  │ • Settlement View   │  │ • Analytics        │  │
│  └─────────┬──────────┘  └─────────┬──────────┘  └─────────┬──────────┘  │
└────────────┼─────────────────────────┼─────────────────────────┼──────────┘
             │                         │                         │
             │     Sync when online    │                         │
             ▼                         ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         API GATEWAY LAYER                                │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  FastAPI Application (app/main.py)                                  │ │
│  │  • Rate Limiting • CORS • Authentication • Request Validation     │ │
│  │  • Device Blacklist Middleware • Correlation ID Tracking            │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         SERVICE LAYER                                    │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │
│  │ AuthService │ │ TokenService│ │Transaction │ │ Settlement │       │
│  │             │ │             │ │ Service    │ │ Service    │       │
│  │ User mgmt   │ │ Provision   │ │ Sync batch │ │ Nomba API  │       │
│  │ OTP verify  │ │ Revoke      │ │ Verify sig │ │ Transfer   │       │
│  │ PIN verify  │ │ Track usage │ │ Fraud check│ │ Retry logic│       │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘       │
│         │               │               │               │               │
│  ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐       │
│  │WalletService│ │DeviceTrust │ │FraudService│ │Notification│       │
│  │             │ │ Service    │ │             │ │ Service    │       │
│  │ Virtual Acct│ │ Play Integ │ │ Checkpoint 1│ │ Real-time  │       │
│  │ Funding     │ │ Trust score│ │ Checkpoint 2│ │ Supabase   │       │
│  │ Balance     │ │ Limits     │ │ Auto-block  │ │ push       │       │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘       │
│         │               │               │               │               │
│  ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐       │
│  │LedgerService│ │IdentityVer │ │SupabaseSvc │ │AuditService │       │
│  │             │ │ Service    │ │            │ │             │       │
│  │ Credit/Debit│ │ NIN/BVN    │ │ Auth       │ │ Append-only │       │
│  │ Lock/Unlock │ │ Face match │ │ JWT verify │ │ Audit log   │       │
│  │ Integrity   │ │ Gate tokens│ │ Sessions   │ │             │       │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                       │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐ │
│  │   PostgreSQL       │  │      Redis         │  │   External APIs    │ │
│  │                    │  │                    │  │                    │ │
│  │ • Users           │  │ • Nonce tracking  │  │ • Nomba API       │ │
│  │ • Devices         │  │ • Sequence nums   │  │ • Supabase        │ │
│  │ • Offline Tokens  │  │ • Rate limiting   │  │   (Auth, Realtime)│ │
│  │ • Transactions    │  │ • Token caching   │  │                    │ │
│  │ • Settlements     │  │ • OTP storage     │  │                    │ │
│  │ • Ledger Entries  │  │ • PIN attempts    │  │                    │ │
│  │ • Fraud Signals   │  │                    │  │                    │ │
│  │ • Notifications   │  │                    │  │                    │ │
│  │ • Audit Log       │  │                    │  │                    │ │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### Background Workers (Celery Beat)

| Task | Schedule | Purpose |
|------|----------|---------|
| `expire_tokens` | Hourly | Refund unused balance from expired tokens |
| `apply_spend_cutoffs` | 15 min | Lock spending on tokens past 48h cutoff |
| `scan_for_blacklist_candidates` | 30 min | Auto-blacklist devices meeting fraud threshold |
| `capture_balance_snapshot` | Daily | Record Nomba treasury balance for reconciliation |
| `recalculate_device_trust_scores` | Daily | Update device trust scores from activity |
| `run_reconciliation` | Daily | Compare Nomba transactions with local ledger |
| `retry_failed_settlements` | 5 min | Retry pending/failed bank transfers |

---

## Offline Payment Flow

```
Customer (Offline)                    Merchant (Offline)
      │                                      │
      │  1. Generate Transaction             │
      │  • Create tx with ULID ID            │
      │  • Sign with Ed25519 private key     │
      │  • Include nonce + sequence #        │
      │                                      │
      │  2. QR/BLE Exchange                  │
      │◄─────────────────────────────────────┤
      │     Transaction Request              │
      ├─────────────────────────────────────►│
      │     Transaction Payload              │
      │     • Amount, token_id               │
      │     • Customer signature             │
      │                                      │
      │  3. Merchant Verifies                │
      │     • Verify customer signature      │
      │     • Check token not exhausted     │
      │     • Create receipt signature      │
      │                                      │
      │  4. Both Store Locally               │
      │     • Append to local sqlite        │
      │     • Update spent amount            │
      │                                      │
      └──────────────────────────────────────┘
                    ...
             (When Online)
                    ...

Backend Server                              Nomba API
      │                                        │
      │  5. Transaction Sync                  │
      │◄───────────────────────────────────────┤
      │  POST /v1/transactions/sync           │
      │  • Batch of signed transactions       │
      │  • Merchant device signature          │
      │                                        │
      │  6. Verify & Process                   │
      │  • Check nonce uniqueness            │
      │  • Verify all signatures             │
      │  • Run fraud checkpoint               │
      │                                        │
      │  7. Settlement                         │
      │  ├────────────────────────────────────►│
      │  │  POST /transfers/bank               │
      │  │  • Lookup account first             │
      │  │  • Initiate transfer                │
      │  │  • Get merchantTxRef                │
      │  │                                      │
      │  8. Webhook (async)                    │
      │◄─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
      │     Transfer completed/failed         │
      │     • Update settlement status         │
      │     • Notify user                     │
      │                                        │
      └────────────────────────────────────────┘
```

---

## Quick Start

### Docker (Recommended)

```bash
# Clone repository
git clone https://github.com/diamondBelema/offimesh.git
cd offimesh

# Copy environment template
cp .env.example .env
# Edit .env with your credentials (Nomba, Supabase, JWT keys)

# Start services with Docker
docker-compose up -d

# Run migrations
docker-compose exec app alembic upgrade head

# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Run migrations
alembic upgrade head

# Start development server
python -m app.main
```

### Running Workers

```bash
# Celery worker
celery -A app.workers.celery_app worker --loglevel=info

# Celery beat scheduler
celery -A app.workers.celery_app beat --loglevel=info
```

---

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL async connection URL | Yes |
| `REDIS_URL` | Redis connection URL | Yes |
| `CELERY_BROKER_URL` | Redis URL for Celery | Yes |
| `JWT_PRIVATE_KEY` | RS256 private key (PEM format) | Yes |
| `JWT_PUBLIC_KEY` | RS256 public key (PEM format) | Yes |
| `NOMBA_ACCOUNT_ID` | Nomba parent account ID | Yes |
| `NOMBA_CLIENT_ID` | Nomba OAuth client ID | Yes |
| `NOMBA_CLIENT_SECRET` | Nomba OAuth secret | Yes |
| `NOMBA_WEBHOOK_SECRET` | Webhook signing secret | Yes |
| `SUPABASE_URL` | Supabase project URL | For auth/notifications |
| `SUPABASE_ANON_KEY` | Supabase anonymous key | For auth/notifications |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | For auth/notifications |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret | For token verification |
| `ENVIRONMENT` | development/staging/production | No |
| `DEBUG` | Enable debug mode | No |

---

## Database Schema

All monetary values stored as `BIGINT` in **kobo** (1/100 of Naira). Never use float/decimal for money.

### Core Tables

| Table | Description |
|-------|-------------|
| `users` | Customer/merchant accounts with encrypted phone, NIN/BVN status |
| `devices` | Registered devices with Ed25519 public keys, trust scores |
| `offline_tokens` | Pre-authorized spending tokens with two-clock TTL |
| `transactions` | Payment records with Ed25519 signatures |
| `settlements` | Settlement tracking via Nomba |
| `settlement_claims` | Anti-double-spend via UNIQUE settlement_serial |
| `virtual_accounts` | Wallet funding NUBAN accounts |

### Ledger Tables

| Table | Description |
|-------|-------------|
| `ledger_balances` | Current available + locked amounts per user |
| `ledger_entries` | Append-only credit/debit entries with balance snapshots |

### Fraud & Security Tables

| Table | Description |
|-------|-------------|
| `fraud_signals` | Signal type, score, checkpoint, device fingerprint |
| `blacklisted_devices` | Hash-banned devices with reason |
| `device_activity_log` | IP, GPS, Play Integrity verdict per action |

### Identity Tables

| Table | Description |
|-------|-------------|
| `identity_verifications` | NIN/BVN status, face match score |

### Notification Tables

| Table | Description |
|-------|-------------|
| `notifications` | User alerts for transactions, security, etc. |
| `notification_preferences` | Per-user notification type preferences |

### Treasury Tables

| Table | Description |
|-------|-------------|
| `nomba_sub_accounts` | Operational treasury sub-account |
| `sub_account_balance_snapshots` | Daily balance snapshots for reconciliation |

### System Tables

| Table | Description |
|-------|-------------|
| `webhook_events` | Idempotent webhook storage |
| `audit_log` | Append-only audit trail |

---

## API Endpoints Summary

### Authentication
- `POST /v1/auth/register` - Register with phone
- `POST /v1/auth/verify-otp` - Verify OTP
- `POST /v1/auth/login` - Request login OTP
- `POST /v1/auth/token` - Exchange OTP for tokens
- `POST /v1/auth/refresh` - Refresh access token
- `POST /v1/auth/pin/create` - Create transaction PIN
- `POST /v1/auth/pin/verify` - Verify PIN (rate-limited 5/15min)

### Supabase Auth
- `POST /v1/auth/supabase/signup` - Create account with email/password
- `POST /v1/auth/supabase/signin` - Sign in with email/password
- `POST /v1/auth/supabase/refresh` - Refresh Supabase session
- `POST /v1/auth/supabase/verify` - Verify Supabase JWT
- `POST /v1/auth/supabase/signout` - Sign out

### Identity Verification
- `POST /v1/users/identity/initiate` - Start NIN/BVN verification
- `POST /v1/users/identity/face-verify` - Verify face matches ID
- `GET /v1/users/identity/status` - Get verification status
- `GET /v1/users/identity/can-provision-token` - Check token eligibility

### Tokens
- `POST /v1/tokens/provision` - Provision offline spending token
- `GET /v1/tokens/active` - List active tokens
- `GET /v1/tokens/{id}/status` - Get token status
- `POST /v1/tokens/{id}/revoke` - Revoke token

### Transactions
- `POST /v1/transactions/sync` - Batch sync transactions
- `GET /v1/transactions` - List user transactions
- `GET /v1/transactions/{id}` - Get transaction details

### Wallet
- `GET /v1/wallet/balance` - Get wallet balance
- `POST /v1/wallet/fund` - Generate virtual account
- `GET /v1/wallet/funding-status` - Check funding status

### Notifications
- `GET /v1/notifications` - List notifications
- `GET /v1/notifications/unread-count` - Get unread count
- `POST /v1/notifications/{id}/read` - Mark as read
- `POST /v1/notifications/mark-all-read` - Mark all read
- `GET /v1/notifications/preferences` - Get preferences
- `PUT /v1/notifications/preferences` - Update preferences

### Webhooks
- `POST /v1/webhooks/nomba` - Receive Nomba webhook events

---

## Reconciliation

**Critical safeguard against silent money loss.**

The reconciliation worker runs nightly:
1. Pulls all transactions from Nomba API for the day
2. Builds lookup map by `merchantTxRef` (our tx_id)
3. Compares against local transactions table
4. Reports:
   - Missing in local (shouldn't happen)
   - Missing in Nomba
   - Amount mismatches
   - Status discrepancies

Any discrepancy triggers alerts for manual review.

---

## Security Measures

1. **Replay Attack Prevention**
   - Every transaction has unique nonce stored in Redis (SETNX)
   - Redis + DB unique constraints on nonce

2. **Double-Spend Prevention**
   - UNIQUE constraint on `settlement_serial`
   - First DB commit wins, others get conflict error
   - PostgreSQL advisory locks for concurrent settlement

3. **Device Trust Verification**
   - Google Play Integrity API verification
   - Trust score (0-100) based on device history
   - Low trust = blocked transactions

4. **Fraud Detection**
   - Two checkpoint system
   - Auto-blacklisting at threshold
   - Machine learning signals (future)

5. **Money Integrity**
   - Double-entry ledger
   - Balance integrity verification API
   - Nightly reconciliation

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run linting: `ruff check app/`
5. Run type checking: `mypy app/`
6. Submit a pull request

---

## License

MIT License - See LICENSE file for details.

---

## Author

Built by Diamond Belema and David Briggs for the Dev career nomba hackathon.

OffiMesh - Extending digital payments to the offline world.
