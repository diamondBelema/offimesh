# OffiMesh API Reference

**Base URL:** `https://offimesh.claudy.name.ng/v1`

All monetary values are in **kobo** (1 Naira = 100 kobo).

---

## Standard Response Envelope

Every endpoint returns this envelope:

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-07-07T12:00:00.000000Z",
    "version": "1.0"
  }
}
```

Errors:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "field": null
  },
  "meta": { "request_id": "...", "timestamp": "...", "version": "1.0" }
}
```

---

## Authentication

### Flow
```
1. POST /v1/auth/register       → OTP sent via SMS
2. POST /v1/auth/verify-otp     → Account activated
3. POST /v1/auth/token           → Get access/refresh tokens
4. POST /v1/auth/refresh         → Refresh expired token
```

All protected endpoints require:
```
Authorization: Bearer <access_token>
```

Access tokens: RS256 JWT, 15-minute TTL.
Refresh tokens: 7-day TTL.

---

### POST /v1/auth/register

Register a new user. Creates a Nomba virtual account automatically.

**Request:**
```json
{
  "phone": "2348012345678",
  "name": "John Adebayo",
  "role": "customer"
}
```

| Field  | Type   | Required | Description                |
|--------|--------|----------|----------------------------|
| phone  | string | yes      | 10-15 chars, starts with 234 |
| name   | string | no       | Max 255 chars              |
| role   | string | no       | `customer` or `merchant`, default `customer` |

**Response:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "otp_sent": true,
  "message": "OTP sent to your phone"
}
```

The user's wallet virtual account details are stored server-side and can be retrieved later via `GET /v1/wallet/account`.

> Internally, this virtual account is created via Nomba's `POST /v1/accounts/virtual/{subAccountId}` — scoped to our team's sub-account, not the parent account. See "Nomba Integration Architecture" below.

---

### POST /v1/auth/verify-otp

Verify the 6-digit OTP sent during registration.

**Request:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "otp": "123456"
}
```

| Field   | Type   | Required | Description    |
|---------|--------|----------|----------------|
| user_id | string | yes      | UUID from register |
| otp     | string | yes      | 6-digit code   |

**Response:**
```json
{
  "verified": true,
  "user_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### POST /v1/auth/login

Send OTP for existing user login.

**Request:**
```json
{
  "phone": "2348012345678"
}
```

**Response:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "otp_sent": true
}
```

---

### POST /v1/auth/token

Exchange login OTP for access and refresh tokens.

**Request:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "otp": "123456"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 900
}
```

`expires_in` is seconds (15 minutes).

---

### POST /v1/auth/refresh

Get a new access token using a refresh token.

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJSUzI1NiIs..."
}
```

**Response:** Same structure as `/token`.

---

### POST /v1/auth/pin/create

Set a 4-6 digit transaction PIN.

**Auth:** Bearer token required.

**Request:**
```json
{
  "pin": "1234"
}
```

**Response:**
```json
{
  "pin_set": true
}
```

---

### POST /v1/auth/pin/verify

Verify transaction PIN. Rate limited: 5 attempts per 15 minutes.

**Auth:** Bearer token required.

**Request:**
```json
{
  "pin": "1234"
}
```

**Response:**
```json
{
  "verified": true,
  "remaining_attempts": 5
}
```

---

### GET /v1/auth/me

Get the current authenticated user's profile.

**Auth:** Bearer token required.

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "John Adebayo",
  "phone": "***5678",
  "email": null,
  "role": "customer",
  "trust_level": "standard",
  "status": "active",
  "bvn_verified": false,
  "created_at": "2026-07-07T12:00:00+00:00"
}
```

---

## Supabase Auth (Alternative)

Alternative authentication path using Supabase email/password.

### POST /v1/auth/supabase/signup

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword",
  "name": "John Adebayo"
}
```

**Response:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "message": "Account created successfully"
}
```

### POST /v1/auth/supabase/signin

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user": { ... }
}
```

### POST /v1/auth/supabase/refresh

**Request:**
```json
{
  "refresh_token": "eyJ..."
}
```

### POST /v1/auth/supabase/verify

Verify a Supabase JWT token.

**Request:**
```json
{
  "token": "eyJ..."
}
```

### POST /v1/auth/supabase/signout

**Auth:** Bearer token required. Invalidates the Supabase session.

---

## Users

### GET /v1/users/me

Current user profile (alias for `GET /v1/auth/me`).

**Auth:** Bearer token required.

### PATCH /v1/users/me

Update current user's name or email.

**Auth:** Bearer token required.

**Request:**
```json
{
  "name": "New Name",
  "email": "new@email.com"
}
```

Both fields optional.

### GET /v1/users/me/balance

Get wallet balance.

**Auth:** Bearer token required.

**Response:**
```json
{
  "available_balance_kobo": 500000,
  "ledger_balance_kobo": 500000,
  "locked_in_tokens_kobo": 0,
  "pending_settlements_kobo": 0,
  "last_updated": "2026-07-07T12:00:00+00:00"
}
```

### GET /v1/users/me/limits

Get user transaction and token limits.

**Auth:** Bearer token required.

**Response:**
```json
{
  "daily_limit_kobo": 1000000,
  "monthly_limit_kobo": 10000000,
  "per_transaction_limit_kobo": 5000000,
  "offline_token_max_limit_kobo": 500000
}
```

---

## Identity Verification (KYC)

Required before provisioning offline tokens. Flow: Verify NIN (or BVN) → Face verification.

### POST /v1/users/identity/initiate

**Auth:** Bearer token required.

**Request:**
```json
{
  "id_type": "nin",
  "id_number": "12345678901"
}
```

| Field    | Type   | Required | Description             |
|----------|--------|----------|-------------------------|
| id_type  | string | yes      | `nin` or `bvn`          |
| id_number| string | yes      | 10-20 digit ID number   |

**Response:**
```json
{
  "verification_id": "550e8400-e29b-41d4-a716-446655440001",
  "id_type": "nin",
  "status": "verified"
}
```

> Hackathon mode auto-verifies. Production integrates with Dojah/Smile Identity.

### POST /v1/users/identity/face-verify

**Auth:** Bearer token required.

**Request:**
```json
{
  "id_type": "nin",
  "selfie_image_base64": "data:image/jpeg;base64,/9j/4AAQ..."
}
```

**Response:**
```json
{
  "verification_id": "550e8400-e29b-41d4-a716-446655440001",
  "id_type": "nin",
  "status": "verified",
  "face_match_score": 95.0,
  "face_verified": true,
  "message": "Face verification completed"
}
```

> Hackathon mode always returns 95% match. Production uses Smile Identity.

### GET /v1/users/identity/status

**Auth:** Bearer token required.

**Response:**
```json
{
  "nin_verified": true,
  "bvn_verified": false,
  "face_verified": true,
  "can_provision_offline_token": true
}
```

### GET /v1/users/identity/can-provision-token

Check eligibility for offline token provisioning.

**Auth:** Bearer token required.

**Response:**
```json
{
  "can_provision": true,
  "reason": "",
  "requirements": []
}
```

Requirements list (e.g., `["NIN verification required", "Face verification required"]`) if not eligible.

### GET /v1/users/identity/{id_type}/details

Get detailed verification info for NIN or BVN.

**Auth:** Bearer token required.

---

## Devices

### POST /v1/devices/register

Register a new device for offline token signing.

**Auth:** Bearer token required.

**Request:**
```json
{
  "device_fingerprint": "abc123def456...",
  "device_public_key": "ed25519-public-key-in-hex...",
  "attestation_token": "...",
  "device_name": "iPhone 15 Pro",
  "device_type": "ios"
}
```

| Field              | Type   | Required | Description                              |
|--------------------|--------|----------|-------------------------------------------|
| device_fingerprint | string | yes      | 16-128 chars, from device attestation    |
| device_public_key  | string | yes      | Ed25519 public key, min 64 chars         |
| attestation_token  | string | no       | Platform attestation (Apple/Android)     |
| device_name        | string | no       | Max 255 chars                            |
| device_type        | string | no       | `ios`, `android`, or `web`               |

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440003",
  "device_name": "iPhone 15 Pro",
  "device_type": "ios",
  "trust_level": "standard",
  "registered_at": "2026-07-07T12:00:00+00:00"
}
```

### GET /v1/devices

List all devices for the current user.

**Auth:** Bearer token required.

**Response:**
```json
{
  "devices": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440003",
      "device_name": "iPhone 15 Pro",
      "device_type": "ios",
      "trust_level": "standard",
      "last_seen_at": "2026-07-07T12:00:00+00:00",
      "registered_at": "2026-07-07T12:00:00+00:00"
    }
  ],
  "total": 1
}
```

### DELETE /v1/devices/{device_id}

Revoke a device. It can no longer sign transactions.

**Auth:** Bearer token required.

---

## Wallet

### GET /v1/wallet/balance

Alias for `GET /v1/users/me/balance`.

**Auth:** Bearer token required.

### GET /v1/wallet/account

Get the user's primary virtual account (created at registration).

**Auth:** Bearer token required.

**Response:**
```json
{
  "nuban": "9876543210",
  "bank_name": "Nombank MFB",
  "account_name": "John Adebayo",
  "status": "active"
}
```

Deposit funds by transferring to this NUBAN — they auto-credit the wallet.

### POST /v1/wallet/fund

Create a dedicated virtual account for a specific expected amount.

**Auth:** Bearer token required.

**Request:**
```json
{
  "expected_amount_kobo": 500000
}
```

| Field                | Type | Required | Description                       |
|----------------------|------|----------|-----------------------------------|
| expected_amount_kobo | int  | no       | Min 10000 (₦100), Max 100,000,000 |

**Response:**
```json
{
  "id": "uuid",
  "nuban": "9876543210",
  "account_name": "John Adebayo",
  "bank_name": "Nombank MFB",
  "expected_amount_kobo": 500000,
  "status": "active",
  "created_at": "2026-07-07T12:00:00+00:00",
  "expires_at": "2026-07-09T12:00:00+00:00"
}
```

### GET /v1/wallet/fund/{account_id}

Get funding status for a specific funding account.

**Auth:** Bearer token required.

**Response:**
```json
{
  "account_id": "uuid",
  "nuban": "9876543210",
  "status": "active",
  "expected_amount_kobo": 500000,
  "received_amount_kobo": 0,
  "created_at": "2026-07-07T12:00:00+00:00"
}
```

---

## Offline Tokens

Tokens enable offline payments. They are provisioned online, spent offline, and synced later.

Token lifecycle:
1. **active** — Can be spent offline
2. **exhausted** — All funds spent
3. **expired** — Past `expires_at`
4. **revoked** — Manually revoked
5. **spend_locked** — Past `customer_spend_cutoff` (pre-expiry lock)

Two-clock TTL system:
- `customer_spend_cutoff`: 48h from issuance — device stops authorizing spends
- `expires_at`: 72h from issuance — token dead, unused balance refunded

### POST /v1/tokens/provision

Provision a new offline spending token.

**Auth:** Bearer token required.
**Requires:** NIN verified AND face verified.

**Request:**
```json
{
  "requested_limit_kobo": 50000,
  "device_id": "device-uuid"
}
```

| Field                | Type   | Required | Description                   |
|----------------------|--------|----------|--------------------------------|
| requested_limit_kobo | int    | yes      | Min 1000, Max 500,000         |
| device_id            | string | no       | Bind to specific device UUID  |

**Response:**
```json
{
  "token_id": "550e8400-e29b-41d4-a716-446655440002",
  "amount_kobo": 50000,
  "amount_used_kobo": 0,
  "remaining_kobo": 50000,
  "status": "active",
  "expires_at": "2026-07-09T12:00:00+00:00",
  "server_signature": "base64-encoded-signature"
}
```

The `server_signature` is used by the device to verify the token was legitimately issued.

### GET /v1/tokens/active

List all active offline tokens for the current user.

**Auth:** Bearer token required.

**Response:**
```json
{
  "tokens": [
    {
      "token_id": "uuid",
      "amount_kobo": 50000,
      "remaining_kobo": 45000,
      "expires_at": "2026-07-09T12:00:00+00:00",
      "status": "active",
      "device_id": "device-uuid"
    }
  ],
  "total": 1
}
```

### DELETE /v1/tokens/{token_id}

Revoke an offline token. Any unused balance is refunded.

**Auth:** Bearer token required.

---

## Transactions

### POST /v1/transactions/sync

Sync a batch of offline transactions to the server.

**Auth:** Bearer token required.

**Request:**
```json
{
  "batch_id": "batch-ulid-001",
  "device_id": "device-uuid",
  "transactions": [
    {
      "tx_id": "01ARXYZ...",
      "token_id": "550e8400-e29b-41d4-a716-446655440002",
      "payer_user_id": "payer-uuid",
      "payee_user_id": "payee-uuid",
      "amount_kobo": 10000,
      "currency": "NGN",
      "merchant_reference": "INV-001",
      "nonce": "64-char-unique-nonce...",
      "sequence_number": 1,
      "initiated_at": "2026-07-07T12:00:00Z",
      "payer_signature": "base64-signature...",
      "merchant_signature": "base64-signature...",
      "payload_hash": "sha256-hex..."
    }
  ],
  "device_signature": "ed25519-signature-of-batch-payload"
}
```

| Field            | Type   | Required | Description                        |
|------------------|--------|----------|-------------------------------------|
| batch_id         | string | yes      | Unique batch ULID                  |
| device_id        | string | yes      | Device that processed the batch    |
| transactions     | array  | yes      | Max 100 items                      |
| device_signature | string | yes      | Ed25519 signature of batch payload |

Per-transaction fields:

| Field              | Type   | Required | Description               |
|--------------------|--------|----------|----------------------------|
| tx_id              | string | yes      | ULID transaction ID       |
| token_id           | string | yes      | Offline token used        |
| payer_user_id      | string | yes      | Payer UUID                |
| payee_user_id      | string | yes      | Merchant UUID              |
| amount_kobo        | int    | yes      | Min 100, Max 5,000,000    |
| nonce              | string | yes      | Exactly 64 chars, unique  |
| sequence_number    | int    | yes      | Monotonically increasing  |
| payer_signature    | string | yes      | Payer's Ed25519 signature |
| merchant_signature | string | yes      | Merchant's Ed25519 sig    |
| payload_hash       | string | yes      | SHA-256 hex, 64 chars     |

The server validates:
1. Device signature of the batch payload
2. Each transaction's payer and merchant signatures
3. Nonce uniqueness (replay protection)
4. Sequence number ordering per device
5. Token validity and available balance
6. Fraud checkpoints

**Response:**
```json
{
  "batch_id": "batch-ulid-001",
  "processed": 5,
  "accepted": 4,
  "rejected": 1,
  "results": [
    { "tx_id": "...", "status": "accepted", "reason": null },
    { "tx_id": "...", "status": "rejected", "reason": "insufficient_balance" }
  ]
}
```

### GET /v1/transactions

List the current user's transactions (payer or payee).

**Auth:** Bearer token required.

**Query Parameters:**
| Param     | Type   | Default | Description        |
|-----------|--------|---------|--------------------|
| page      | int    | 1       | Page number        |
| page_size | int    | 20      | Per page (max 100) |
| status    | string | null    | Filter by status   |

**Response:**
```json
{
  "items": [
    {
      "tx_id": "01ARXYZ...",
      "payer_user_id": "payer-uuid",
      "payee_user_id": "payee-uuid",
      "amount_kobo": 10000,
      "currency": "NGN",
      "status": "verified",
      "merchant_reference": "INV-001",
      "initiated_at": "2026-07-07T12:00:00+00:00",
      "synced_at": "2026-07-07T12:05:00+00:00",
      "settled_at": null
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "has_next": true
}
```

### GET /v1/transactions/{tx_id}

Get a single transaction by ID.

**Auth:** Bearer token required. User must be payer or payee.

**Response:** Same structure as item above + `nomba_reference`, `fraud_score`, `created_at`.

### GET /v1/transactions/{tx_id}/events

Get event history for a transaction (creation, status changes, settlement attempts, etc.).

**Auth:** Bearer token required.

---

## Settlements

Settlements transfer funds from the OffiMesh Nomba account to a merchant's bank account.

### GET /v1/settlements

List all settlements.

**Auth:** Bearer token required (admin).

**Query Parameters:**
| Param     | Type   | Default | Description        |
|-----------|--------|---------|--------------------|
| page      | int    | 1       | Page number        |
| page_size | int    | 20      | Per page (max 100) |
| status    | string | null    | Filter by status   |

**Response:**
```json
{
  "items": [
    {
      "id": "settlement-uuid",
      "tx_id": "01ARXYZ...",
      "amount_kobo": 10000,
      "status": "completed",
      "nomba_transfer_id": "TRF-xxx",
      "attempts": 1,
      "settled_at": "2026-07-07T12:10:00+00:00",
      "created_at": "2026-07-07T12:05:00+00:00"
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 20,
  "has_next": false
}
```

### GET /v1/settlements/{tx_id}

Get settlement details for a specific transaction.

**Auth:** Bearer token required (admin).

**Response:**
```json
{
  "id": "settlement-uuid",
  "tx_id": "01ARXYZ...",
  "nomba_transfer_id": "TRF-xxx",
  "amount_kobo": 10000,
  "fee_kobo": 15,
  "status": "completed",
  "attempts": 1,
  "last_attempt_at": "2026-07-07T12:10:00+00:00",
  "settled_at": "2026-07-07T12:10:00+00:00",
  "error_code": null,
  "error_message": null,
  "created_at": "2026-07-07T12:05:00+00:00"
}
```

### POST /v1/settlements/{tx_id}/process

Trigger settlement for a transaction.

**Auth:** Bearer token required (admin).

**Response:**
```json
{
  "tx_id": "01ARXYZ...",
  "success": true,
  "nomba_reference": "TRF-xxx",
  "status": "settled",
  "message": null
}
```

Settlement flow:
1. Look up merchant's bank account (`POST /v1/transfers/bank/lookup`)
2. Initiate transfer via Nomba API (`POST /v2/transfers/bank`)
3. Persist the returned Nomba transfer `id` immediately — it's required for any later status requery, since Nomba doesn't support looking a transfer up purely by our own `merchantTxRef`
4. Mark settlement as complete on success
5. Failed settlements retry automatically (Celery task every 5 min, max 3 retries)
6. Webhooks from Nomba update settlement status in real time

---

## Webhooks

### POST /v1/webhooks/nomba

Receive webhook events from Nomba (wallet funding, transfer success/failure).

**No auth required** (HMAC-SHA256 signature verification in place of bearer auth).

**Headers:**
| Header            | Required | Description                                        |
|-------------------|----------|-----------------------------------------------------|
| nomba-signature   | yes      | HMAC-SHA256 signature, **base64-encoded** (not hex)  |
| nomba-timestamp   | yes      | Timestamp used as the final component of the signed string — required input to signature verification, not just metadata |

**Signature verification:** the signature is **not** a hash of the raw request body. It's an HMAC-SHA256 (base64-encoded) over a colon-joined string built from specific parsed payload fields, with `nomba-timestamp` appended as the last component:

```
event_type:requestId:userId:walletId:transactionId:type:time:responseCode:timestamp
```

`userId`/`walletId` come from `data.merchant`; `transactionId`/`type`/`time`/`responseCode` come from `data.transaction`. A literal `"null"` responseCode is normalized to an empty string before signing.

**Payload (Nomba's real shape — note this uses `event_type`, not `event`, and nests fields under `data.merchant` / `data.transaction`, not flat top-level keys):**
```json
{
  "requestId": "evt_123",
  "event_type": "payment_success",
  "data": {
    "merchant": {
      "walletId": "...",
      "walletBalance": 120450,
      "userId": "..."
    },
    "transaction": {
      "transactionId": "...",
      "type": "vact_transfer",
      "transactionAmount": 500,
      "aliasAccountReference": "OFFIMESH_...",
      "aliasAccountType": "VIRTUAL",
      "aliasAccountNumber": "9876543210",
      "responseCode": "",
      "time": "2026-07-07T12:00:00Z"
    },
    "customer": {
      "senderName": "...",
      "accountNumber": "...",
      "bankName": "...",
      "bankCode": "..."
    }
  },
  "timestamp": "2026-07-07T12:00:00Z"
}
```

`data.transaction.aliasAccountReference` is the correlation key back to our own `accountRef` (set when we created the virtual account) — this is how a `payment_success` event is matched to the right user. `data.transaction.aliasAccountType == "VIRTUAL"` distinguishes a virtual-account wallet top-up from other `payment_success` sources (e.g. POS/card).

**Events handled (real Nomba `event_type` values):**

| Event              | Action                                                                 |
|--------------------|-------------------------------------------------------------------------|
| `payment_success`  | If `aliasAccountType == "VIRTUAL"`: credit user wallet, create ledger entry |
| `payout_success`   | Mark settlement completed                                              |
| `payment_failed`   | Mark related settlement/payment failed                                 |
| `payout_failed`    | Mark settlement failed, trigger retry                                  |
| `payment_reversal` | Logged; requires explicit handling (not yet wired to a service action) |
| `payout_refund`    | Logged; requires explicit handling (not yet wired to a service action) |

**Response (success or already-seen duplicate):**
```json
{
  "received": true,
  "request_id": "evt_123"
}
```

**Status code semantics — this endpoint does NOT always return 200:**
- `200` — acknowledged: either processed successfully, or a known duplicate `requestId` (Nomba should stop retrying).
- `401` — signature verification failed. If this happens for a genuine Nomba webhook rather than a forged request, it means our signature verification is broken (e.g. missing/wrong `nomba-timestamp`), not that the sender is invalid.
- `500` — genuine processing failure. Deliberately **not** swallowed to 200, so Nomba retries (up to 5 times, exponential backoff) and we get another chance once the transient issue clears.

### GET /v1/webhooks/events

List webhook events (for debugging).

**Auth:** Bearer token required (admin).

---

## Notifications

### GET /v1/notifications

List user notifications.

**Auth:** Bearer token required.

**Query Parameters:**
| Param       | Type    | Default | Description            |
|-------------|---------|---------|------------------------|
| limit       | int     | 20      | Max 100                |
| offset      | int     | 0       | Pagination offset      |
| unread_only | boolean | false   | Filter unread only     |

**Response:**
```json
{
  "notifications": [
    {
      "id": "notif-uuid",
      "notification_type": "transaction_received",
      "title": "Payment Received",
      "message": "You received ₦10,000 from John",
      "data": { "tx_id": "..." },
      "read_at": null,
      "created_at": "2026-07-07T12:00:00+00:00"
    }
  ],
  "unread_count": 3,
  "total": 20
}
```

### GET /v1/notifications/unread-count

**Response:** `{"unread_count": 3}`

### POST /v1/notifications/{notification_id}/read

Mark a single notification as read.

### POST /v1/notifications/mark-all-read

Mark all notifications as read.

**Response:** `{"success": true, "marked_count": 5}`

### GET /v1/notifications/preferences

Get notification preferences.

**Response:**
```json
{
  "push_enabled": true,
  "email_enabled": false,
  "sms_enabled": true,
  "transaction_notifications": true,
  "security_notifications": true,
  "promotional_notifications": false
}
```

### PUT /v1/notifications/preferences

Update notification preferences. All fields optional.

**Request:** Same structure as the response above.

---

## Health

### GET /health

```json
{
  "status": "ok",
  "app": "OffiMesh",
  "version": "1.0.0",
  "environment": "production",
  "timestamp": "2026-07-07T12:00:00+00:00"
}
```

### GET /

```json
{
  "app": "OffiMesh",
  "version": "1.0.0",
  "docs": "/docs",
  "description": "Offline-first payment infrastructure for Africa"
}
```

### GET /v1/health

Same response as `/health`.

---

## Debug

### GET /v1/debug/nomba/verify-webhook-routing

Check if Nomba webhooks are correctly configured for your sub-account.

**Auth:** Bearer token required (admin).

**Response (configured):**
```json
{
  "status": "success",
  "message": "Webhook routing verified successfully",
  "account_holder_id": "acc_xxx",
  "webhook_configured": true
}
```

**Response (not configured):**
```json
{
  "status": "error",
  "message": "Webhook is not properly configured",
  "account_holder_id": null,
  "webhook_configured": false,
  "action_required": true,
  "instructions": "1. Go to Nomba Dashboard > Webhooks & Sub-accounts..."
}
```

---

## Error Codes

| HTTP | Code                     | Description                        |
|------|--------------------------|--------------------------------------|
| 400  | `VALIDATION_ERROR`       | Request body failed validation     |
| 400  | `INVALID_OTP`            | OTP is invalid or expired          |
| 400  | `OTP_EXPIRED`            | OTP has expired                    |
| 400  | `INVALID_PIN`            | PIN verification failed            |
| 400  | `INSUFFICIENT_FUNDS`     | Not enough wallet balance          |
| 400  | `INVALID_SIGNATURE`      | Transaction signature invalid      |
| 400  | `REPLAY_DETECTED`        | Nonce already used                 |
| 401  | `AUTHENTICATION_ERROR`   | Missing or invalid auth token      |
| 401  | `INVALID_TOKEN`          | JWT expired or invalid             |
| 401  | `INVALID_CREDENTIALS`    | Wrong credentials                  |
| 403  | `PERMISSION_DENIED`      | Not authorized for resource        |
| 403  | `FRAUD_BLOCKED`          | Transaction blocked by fraud check |
| 404  | `NOT_FOUND`              | Resource not found                 |
| 409  | `CONFLICT`               | Duplicate entry (e.g., device)     |
| 429  | `RATE_LIMIT_EXCEEDED`    | Too many requests                  |
| 502  | `NOMBA_ERROR`            | Nomba API integration error        |
| 502  | `NOMBA_AUTH_ERROR`       | Nomba authentication failure       |
| 503  | `NOMBA_SERVICE_UNAVAILABLE` | Nomba circuit breaker open     |

---

## Environment Variables

| Variable                        | Default                              | Description                        |
|----------------------------------|--------------------------------------|--------------------------------------|
| `DATABASE_URL`                  | —                                    | PostgreSQL async connection string |
| `REDIS_URL`                     | `redis://localhost:6379/0`           | Redis connection URL               |
| `JWT_PRIVATE_KEY`               | —                                    | RSA private key (PEM)              |
| `JWT_PUBLIC_KEY`                | —                                    | RSA public key (PEM)               |
| `NOMBA_ENVIRONMENT`             | `sandbox`                            | `sandbox` or `production`          |
| `NOMBA_BASE_URL`                | `https://sandbox.nomba.com`          | Bare Nomba API host — **no** `/v1` suffix; each client call adds its own version prefix (`/v1` or `/v2`) |
| `NOMBA_ACCOUNT_ID`              | —                                    | **Parent** Nomba account ID — sent in the `accountId` header on every request |
| `NOMBA_SUBACCOUNT_ID`           | —                                    | Team sub-account ID — passed as a path parameter, never in the header |
| `NOMBA_CLIENT_ID`               | —                                    | Nomba OAuth client ID              |
| `NOMBA_CLIENT_SECRET`           | —                                    | Nomba OAuth client secret          |
| `NOMBA_WEBHOOK_SECRET`          | —                                    | HMAC secret for webhook verification |
| `SMS_PROVIDER`                  | `mock`                               | `africastalking`, `termii`, `mock` |
| `SMS_GATEWAY_API_KEY`           | —                                    | API key for SMS provider           |
| `SMS_GATEWAY_USERNAME`          | `sandbox`                            | Africa's Talking username          |
| `SUPABASE_URL`                  | —                                    | Supabase project URL               |
| `SUPABASE_SERVICE_ROLE_KEY`     | —                                    | Supabase service role key          |

---

## Rate Limits

| Scope         | Limit                      |
|---------------|------------------------------|
| General API   | 100 requests/minute per IP |
| PIN verify    | 5 attempts/15 minutes      |
| Nomba calls   | Circuit breaker: 5 failures in 60s → 30s open, then half-open (per `CircuitBreaker` defaults in `base_client.py`) |

> Note: retries via exponential backoff currently only cover network-level failures (timeouts, connection errors). HTTP-level failures from Nomba (429, 500-504) are not currently retried, despite the retry config defining which status codes should be — a known gap to close before relying on this for production resilience.

Health check (`/health`) and webhook endpoints (`/v1/webhooks/`) bypass rate limiting.

---

## Celery Tasks

Background tasks run on 3 queues: `settlement`, `webhook`, `reconciliation`.

| Task                              | Schedule     | Queue          |
|-----------------------------------|--------------|----------------|
| `expire_tokens`                   | Every 1 hour | default        |
| `apply_spend_cutoffs`             | Every 15 min | default        |
| `scan_for_blacklist_candidates`   | Every 30 min | default        |
| `recalculate_trust_scores`        | Daily        | default        |
| `capture_balance_snapshot`        | Daily        | default        |
| `run_reconciliation`              | Daily        | reconciliation |
| `retry_failed_settlements`        | Every 5 min  | settlement     |
| `process_pending_webhooks`        | On demand    | webhook        |

---

## User Journey (End-to-End)

```
1. REGISTER
   POST /v1/auth/register
   └─→ User created, virtual NUBAN created via Nomba (scoped to our sub-account), OTP sent via SMS

2. VERIFY
   POST /v1/auth/verify-otp
   └─→ Account activated

3. LOGIN
   POST /v1/auth/login → POST /v1/auth/token
   └─→ OTP sent → Access + refresh tokens

4. FUND WALLET
   Transfer money to your virtual NUBAN from any bank
   └─→ Nomba webhook (payment_success, aliasAccountType=VIRTUAL) credits your wallet automatically

5. KYC (required for offline tokens)
   POST /v1/users/identity/initiate (NIN or BVN)
   POST /v1/users/identity/face-verify (selfie)

6. REGISTER DEVICE
   POST /v1/devices/register

7. SET PIN
   POST /v1/auth/pin/create

8. PROVISION TOKEN
   POST /v1/tokens/provision
   └─→ Offline token signed and stored on device

9. MAKE OFFLINE PAYMENT
   No internet needed — token + Ed25519 signatures

10. SYNC
    POST /v1/transactions/sync
    └─→ Batch of signed transactions uploaded when online

11. SETTLEMENT (merchant)
    POST /v1/settlements/{tx_id}/process
    └─→ Nomba transfer to merchant's bank account
```

---

## Nomba Integration Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   OffiMesh Backend                        │
│                                                          │
│  ┌──────────┐  ┌────────────┐  ┌──────────────────┐     │
│  │ Auth     │  │ Transfers  │  │ Transactions      │     │
│  │ Client   │  │ Client     │  │ Client            │     │
│  └────┬─────┘  └─────┬──────┘  └────────┬─────────┘     │
│       │              │                   │               │
│  ┌────▼──────────────▼───────────────────▼──────────┐   │
│  │           BaseNombaClient                         │   │
│  │  - Circuit breaker (5 failures / 60s window)      │   │
│  │  - Retry with exponential backoff                 │   │
│  │    (currently network-level failures only --      │   │
│  │     429/5xx retries not yet wired up)             │   │
│  │  - Redis-cached auth tokens (25-min TTL)          │   │
│  │  - Structured logging + correlation IDs           │   │
│  └───────────────────────┬───────────────────────────┘   │
│                          │                                 │
└──────────────────────────┼─────────────────────────────┘
                           │ HTTPS
              ┌────────────▼────────────┐
              │     Nomba API            │
              │  sandbox.nomba.com       │
              │  api.nomba.com           │
              └─────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │  Sub-account wallet      │
              │  (team's settlement      │
              │   account at Nombank MFB)│
              └─────────────────────────┘
```

**On the `accountId` header vs sub-account:** every request (auth included) sends the shared **parent** hackathon account ID in the `accountId` header. Our team's sub-account ID is a completely separate value, passed as a path parameter on the specific endpoints that support it (e.g. `/v1/accounts/virtual/{subAccountId}`) — never in the header.

### Key Integration Points

| Operation               | Nomba Endpoint                              | Frequency        |
|-------------------------|-----------------------------------------------|-------------------|
| Auth (get token)        | `POST /v1/auth/token/issue`                  | Every 25 min      |
| Create virtual account  | `POST /v1/accounts/virtual/{subAccountId}`   | Per registration  |
| Bank account lookup     | `POST /v1/transfers/bank/lookup`             | Per settlement    |
| Initiate transfer       | `POST /v2/transfers/bank`                    | Per settlement    |
| Filter/list transactions| `POST /v1/transactions/accounts`             | Daily (recon)     |
| Single transaction      | `GET /v1/transactions/accounts/single`       | On demand         |
| Webhook delivery        | Nomba → `POST /v1/webhooks/nomba`            | Real-time         |
| Sub-account balance     | `GET /v1/accounts/{subAccountId}/balance`    | Daily             |
