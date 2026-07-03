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
│  │ JWT tokens  │ │ Track usage │ │ Fraud check│ │ Retry logic│       │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘       │
│         │               │               │               │               │
│  ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐       │
│  │WalletService│ │WebhookSvc  │ │FraudService │ │AuditService │       │
│  │             │ │             │ │(Future)    │ │             │       │
│  │ Virtual Acct│ │ Nomba hook │ │            │ │ Append-only │       │
│  │ Funding     │ │ Handler    │ │            │ │ Audit log   │       │
│  │ Balance     │ │ Signature  │ │            │ │             │       │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                       │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐ │
│  │   PostgreSQL       │  │      Redis         │  │   Nomba API        │ │
│  │                    │  │                    │  │                    │ │
│  │ • Users           │  │ • Nonce tracking  │  │ • Auth token      │ │
│  │ • Devices         │  │ • Sequence nums   │  │ • Virtual accounts│ │
│  │ • Offline Tokens  │  │ • Rate limiting   │  │ • Bank transfers  │ │
│  │ • Transactions    │  │ • Token caching   │  │ • Transactions    │ │
│  │ • Settlements     │  │ • OTP storage     │  │                    │ │
│  │ • Virtual Accounts│  │                    │  │                    │ │
│  │ • Webhook Events  │  │                    │  │                    │ │
│  │ • Audit Log       │  │                    │  │                    │ │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### Offline Payment Flow

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
      │                                      │
      ├─────────────────────────────────────►│
      │     Signed Transaction               │
      │                                      │
      │  3. Merchant Verifies               │
      │     • Check token validity            │
      │     • Verify customer signature      │
      │     • Sign transaction               │
      │                                      │
      │◄─────────────────────────────────────┤
      │     Merchant Signature               │
      │                                      │
      │  4. Both Store Locally               │
      │  • Append to hash-chained ledger     │
      │  • Update token usage                │
      │                                      │
      ▼                                      ▼

When Online - Batch Sync to Server
      │                                      │
      ├─────────────────────────────────────►│
      │  5. POST /v1/transactions/sync       │
      │     • Batch of transactions          │
      │     • Device signature               │
      │                                      │
      │  6. Server Processing                │
      │     • Verify signatures              │
      │     • Check nonces (replay protect)  │
      │     • Verify sequence numbers        │
      │     • Check token status              │
      │     • Store transactions            │
      │                                      │
      ├─── Transaction Status: verified ────►│
      │                                      │
      │  7. Settlement (Background Worker)  │
      │     • Bank account lookup            │
      │     • Initiate transfer via Nomba   │
      │     • Update transaction status     │
      │                                      │
      ▼                                      ▼
```

---

## Project Structure

```
app/
├── core/                    # Application core (no external deps beyond config)
│   ├── config.py            # Environment settings via Pydantic Settings
│   ├── database.py          # Async SQLAlchemy engine + sessions
│   ├── redis.py             # Redis client + helper functions
│   ├── security.py          # Password hashing, JWT, encryption
│   ├── logging.py           # Structured logging with structlog
│   └── exceptions.py        # Centralized exception definitions
│
├── models/                  # SQLAlchemy ORM models (one file per table)
│   ├── user.py              # User model with encrypted phone
│   ├── device.py            # Device model with attestation
│   ├── token.py             # Offline token model
│   ├── transaction.py       # Transaction + TransactionEvent
│   ├── settlement.py        # Settlement tracking
│   ├── virtual_account.py   # Wallet funding NUBAN accounts
│   ├── webhook.py           # Webhook event storage
│   ├── audit.py             # Append-only audit log
│   └── idempotency.py       # Idempotency key storage
│
├── schemas/                 # Pydantic request/response models
│   ├── base.py              # Common response envelope
│   ├── auth.py              # Auth request/response schemas
│   ├── device.py            # Device schemas
│   ├── token.py             # Token schemas
│   ├── transaction.py       # Transaction schemas
│   ├── settlement.py        # Settlement schemas
│   ├── wallet.py            # Wallet schemas
│   ├── webhook.py           # Webhook schemas
│   └── health.py            # Health check schemas
│
├── repositories/           # Data access layer (DB queries only)
│   ├── user_repository.py
│   ├── device_repository.py
│   ├── token_repository.py
│   ├── transaction_repository.py
│   ├── settlement_repository.py
│   ├── virtual_account_repository.py
│   ├── webhook_repository.py
│   └── audit_repository.py
│
├── services/                # Business logic layer
│   ├── auth_service.py      # Registration, OTP, JWT
│   ├── wallet_service.py    # Funding, balance management
│   ├── token_service.py     # Offline token provisioning
│   ├── transaction_service.py  # Sync, verification
│   ├── settlement_service.py   # Nomba settlement
│   └── webhook_service.py   # Nomba webhook handling
│
├── integrations/            # External service clients
│   └── nomba/
│       ├── types.py         # Nomba API types
│       ├── auth.py         # OAuth token caching
│       ├── virtual_accounts.py  # Wallet funding
│       ├── transfers.py    # Bank transfers + circuit breaker
│       ├── transactions.py # Reconciliation queries
│       └── client.py       # Unified client
│
├── workers/                 # Celery background tasks
│   ├── celery_app.py        # Celery configuration
│   ├── settlement_worker.py # Settlement processing + retry
│   ├── webhook_worker.py    # Webhook event processing
│   └── reconciliation_worker.py  # Nightly reconciliation
│
├── routers/                 # FastAPI route definitions
│   ├── auth.py             # /v1/auth/*
│   ├── users.py             # /v1/users/*
│   ├── devices.py           # /v1/devices/*
│   ├── tokens.py            # /v1/tokens/*
│   ├── transactions.py      # /v1/transactions/*
│   ├── settlements.py       # /v1/settlements/*
│   ├── wallet.py            # /v1/wallet/*
│   ├── webhooks.py          # /v1/webhooks/nomba
│   └── health.py            # /health, /v1/health
│
├── middleware/              # FastAPI middleware
│   ├── correlation_id.py    # Request tracing
│   ├── rate_limit.py        # Rate limiting
│   └── auth.py             # JWT verification deps
│
└── main.py                  # Application entry point
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| **Authentication** |||
| POST | `/v1/auth/register` | Register new user (sends OTP) |
| POST | `/v1/auth/verify-otp` | Verify OTP to activate account |
| POST | `/v1/auth/login` | Request login OTP |
| POST | `/v1/auth/token` | Exchange OTP for access token |
| POST | `/v1/auth/refresh` | Refresh access token |
| POST | `/v1/auth/pin/create` | Set transaction PIN |
| **Users** |||
| GET | `/v1/users/me` | Get current user profile |
| PATCH | `/v1/users/me` | Update profile |
| GET | `/v1/users/me/balance` | Get wallet balance |
| GET | `/v1/users/me/limits` | Get transaction limits |
| **Devices** |||
| POST | `/v1/devices/register` | Register device with public key |
| GET | `/v1/devices` | List user's devices |
| DELETE | `/v1/devices/{id}` | Revoke a device |
| **Offline Tokens** |||
| POST | `/v1/tokens/provision` | Provision offline spending token |
| GET | `/v1/tokens/active` | List active tokens |
| DELETE | `/v1/tokens/{id}` | Revoke a token |
| **Transactions** |||
| POST | `/v1/transactions/sync` | Sync batch of offline transactions |
| GET | `/v1/transactions` | List user's transactions |
| GET | `/v1/transactions/{id}` | Get transaction details |
| **Settlements** |||
| GET | `/v1/settlements` | List settlements |
| GET | `/v1/settlements/{tx_id}` | Get settlement status |
| POST | `/v1/settlements/{tx_id}/process` | Trigger settlement |
| **Wallet** |||
| POST | `/v1/wallet/fund` | Create virtual account for funding |
| GET | `/v1/wallet/fund/{id}` | Check funding status |
| GET | `/v1/wallet/balance` | Get wallet balance |
| **Webhooks** |||
| POST | `/v1/webhooks/nomba` | Nomba webhook endpoint |
| **Health** |||
| GET | `/health` | Health check |
| GET | `/` | API info + docs link |

---

## Nomba API Integration

### Authentication
- OAuth client_credentials grant
- Token cached in Redis with 55-minute TTL
- Automatic refresh before expiry

### Virtual Accounts (Wallet Funding)
- Creates dedicated NUBAN for each user
- Customer transfers from any Nigerian bank
- Webhook confirms funding with HMAC verification

### Transfers (Settlements)
1. Bank account name lookup (mandatory)
2. Initiate transfer with merchantTxRef as idempotency key
3. Circuit breaker protects against cascading failures
4. Retry logic with exponential backoff

### Transactions (Reconciliation)
- Nightly job pulls transactions from Nomba
- Diffs against local ledger by merchantTxRef
- Alerts on any discrepancies (critical safeguard)

### Webhook Events Handled
| Event | Action |
|-------|--------|
| `virtual_account.funded` | Credit user wallet, handle over/under payment |
| `transfer.success` | Mark transaction as settled |
| `transfer.failed` | Mark failed, queue for retry |

---

## Security Architecture

### Authentication
- RS256 JWT tokens (not HS256)
- Short-lived access tokens (15 min)
- Refresh token rotation

### Phone Number Storage
- **Never** stored in plaintext
- Scrypt hash with per-user salt (not SHA-256)
- Encrypted version for support lookup (AES-256-GCM)

### Transaction Security
- Ed25519 signatures from both payer and merchant
- 32-byte random nonces for replay protection
- Sequence numbers prevent stale transaction attacks
- PostgreSQL advisory locks prevent concurrent settlement

### Webhook Security
- HMAC-SHA256 signature verification
- Constant-time comparison (timing attack prevention)
- Request ID deduplication before processing

### Rate Limiting
- Per-IP rate limiting with Redis sliding window
- Configurable requests/second

---

## Getting Started

### Prerequisites
- Docker + Docker Compose
- Python 3.12+ (for local development)
- PostgreSQL 16+ (or use Docker)
- Redis 7+ (or use Docker)

### Quick Start

```bash
# Clone repository
git clone https://github.com/diamondBelema/offimesh.git
cd offimesh

# Copy environment template
cp .env.example .env
# Edit .env with your Nomba credentials

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
| `ENVIRONMENT` | development/staging/production | No |
| `DEBUG` | Enable debug mode | No |

---

## Database Schema

All monetary values stored as `BIGINT` in **kobo** (1/100 of Naira). Never use float/decimal for money.

Key tables:
- **users** - Customer/merchant accounts with encrypted phone
- **devices** - Registered devices with Ed25519 public keys
- **offline_tokens** - Pre-authorized spending tokens
- **transactions** - Payment records with Ed25519 signatures
- **settlements** - Settlement tracking via Nomba
- **virtual_accounts** - Wallet funding NUBAN accounts
- **webhook_events** - Idempotent webhook storage
- **audit_log** - Append-only audit trail

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
