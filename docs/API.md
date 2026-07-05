# OffiMesh API Documentation

Complete API reference for the OffiMesh offline payment system.

## Base URL
```
Production: https://api.offimesh.com/v1
Staging: https://staging-api.offimesh.com/v1
Local: http://localhost:8000/v1
```

## Authentication

All protected endpoints require Bearer token authentication:
```
Authorization: Bearer <access_token>
```

## API Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OFFIMESH USER JOURNEY                                │
└─────────────────────────────────────────────────────────────────────────────┘

1. REGISTER
   POST /v1/auth/register
   └─→ User created, OTP sent, Virtual Account created automatically
   └─→ Response: user_id, virtual_account (nuban, bank_name, account_name)

2. VERIFY OTP
   POST /v1/auth/verify-otp
   └─→ Account activated

3. LOGIN (returning user)
   POST /v1/auth/login
   └─→ OTP sent to phone
   
4. GET TOKEN
   POST /v1/auth/token
   └─→ access_token + refresh_token

5. IDENTITY VERIFICATION (KYC)
   POST /v1/users/identity/initiate  (NIN or BVN)
   POST /v1/users/identity/face-verify (Selfie)
   └─→ Required for offline token provisioning

6. SETUP PIN
   POST /v1/auth/pin/create
   └─→ 4-6 digit transaction PIN

7. FUND WALLET
   └─→ Transfer to virtual NUBAN account
   └─→ POST /v1/wallet/fund (optional - for expected amount)

8. PROVISION TOKEN
   POST /v1/tokens/provision
   └─→ Offline payment capability

9. MAKE PAYMENT (offline)
   └─→ Use provisioned token

10. SYNC TRANSACTIONS
    POST /v1/transactions/sync
    └─→ Upload signed transactions when online
```

---

## Authentication Endpoints

### Register User
```http
POST /v1/auth/register
Content-Type: application/json

{
  "phone": "2348012345678",
  "name": "John Adebayo",
  "role": "customer"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "otp_sent": true,
    "message": "OTP sent to your phone",
    "virtual_account": {
      "nuban": "9876543210",
      "bank_name": "Nomba",
      "account_name": "John Adebayo"
    }
  }
}
```

**What happens:**
1. User account created with `pending_verification` status
2. Virtual NUBAN account automatically created via Nomba
3. OTP sent via SMS (or logged in dev mode)
4. User can fund wallet immediately by transferring to NUBAN

---

### Verify OTP
```http
POST /v1/auth/verify-otp
Content-Type: application/json

{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "otp": "123456"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "verified": true,
    "user_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

---

### Login
```http
POST /v1/auth/login
Content-Type: application/json

{
  "phone": "2348012345678"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "otp_sent": true
  }
}
```

---

### Get Access Token
```http
POST /v1/auth/token
Content-Type: application/json

{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "otp": "123456"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "Bearer",
    "expires_in": 900
  }
}
```

---

### Refresh Token
```http
POST /v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

### Create PIN
```http
POST /v1/auth/pin/create
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "pin": "1234"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "pin_set": true
  }
}
```

---

### Verify PIN
```http
POST /v1/auth/pin/verify
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "pin": "1234"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "verified": true,
    "remaining_attempts": 5
  }
}
```

**Rate Limit:** 5 attempts per 15 minutes

---

## Identity Verification (KYC)

### Initiate Verification
```http
POST /v1/users/identity/initiate
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "id_type": "nin",
  "id_number": "12345678901"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "verification_id": "550e8400-e29b-41d4-a716-446655440001",
    "id_type": "nin",
    "status": "verified"
  }
}
```

---

### Face Verification
```http
POST /v1/users/identity/face-verify
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "id_type": "nin",
  "selfie_image_base64": "data:image/jpeg;base64,/9j/4AAQ..."
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "verification_id": "550e8400-e29b-41d4-a716-446655440001",
    "id_type": "nin",
    "status": "verified",
    "face_match_score": 95.0,
    "face_verified": true
  }
}
```

---

### Get Verification Status
```http
GET /v1/users/identity/status
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "nin_verified": true,
    "bvn_verified": false,
    "face_verified": true,
    "can_provision_offline_token": true
  }
}
```

---

## Wallet Endpoints

### Get Balance
```http
GET /v1/wallet/balance
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "balance_kobo": 500000,
    "available_kobo": 500000,
    "pending_kobo": 0
  }
}
```

---

### Get Virtual Account
```http
GET /v1/wallet/account
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "nuban": "9876543210",
    "bank_name": "Nomba",
    "account_name": "John Adebayo",
    "status": "active"
  }
}
```

---

### Create Funding Account (Optional)
```http
POST /v1/wallet/fund
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "expected_amount_kobo": 500000
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "nuban": "9876543210",
    "bank_name": "Nomba",
    "account_name": "John Adebayo",
    "expected_amount_kobo": 500000,
    "expires_at": "2024-01-02T12:00:00Z"
  }
}
```

---

## Token Endpoints

### Provision Offline Token
```http
POST /v1/tokens/provision
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "device_id": "device-uuid-here",
  "requested_limit_kobo": 50000,
  "device_trust_payload": {
    "device_fingerprint": "abc123...",
    "is_hardware_backed_key": true,
    "play_integrity_token": "..."
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "token_id": "550e8400-e29b-41d4-a716-446655440002",
    "serial": "01ARXYZ...",
    "amount_kobo": 50000,
    "status": "active",
    "expires_at": "2024-01-03T12:00:00Z"
  }
}
```

---

### Get Active Tokens
```http
GET /v1/tokens
Authorization: Bearer <access_token>
```

---

### Get Token by Serial
```http
GET /v1/tokens/{serial}
Authorization: Bearer <access_token>
```

---

## Transaction Endpoints

### Sync Offline Transactions
```http
POST /v1/transactions/sync
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "transactions": [
    {
      "tx_id": "01ARXYZ...",
      "payee_user_id": "user-uuid",
      "payee_serial": "01ARABC...",
      "amount_kobo": 10000,
      "nonce": "unique-nonce-123",
      "timestamp": "2024-01-01T12:00:00Z",
      "payer_signature": "base64-signature...",
      "merchant_signature": "base64-signature...",
      "signed_payload_hash": "sha256-hash..."
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "processed": 1,
    "failed": 0,
    "results": [
      {
        "tx_id": "01ARXYZ...",
        "status": "verified"
      }
    ]
  }
}
```

---

### Get Transaction History
```http
GET /v1/transactions?limit=20&offset=0
Authorization: Bearer <access_token>
```

---

## Webhook Endpoints (Nomba Integration)

### Nomba Webhook Handler
```http
POST /v1/webhooks/nomba
Content-Type: application/json
X-Nomba-Signature: <signature>

{
  "eventType": "transfer.successful",
  "eventId": "evt_123",
  "timestamp": "2024-01-01T12:00:00Z",
  "data": {
    "accountId": "9876543210",
    "amount": 50000,
    "reference": "OFFIMESH_..."
  }
}
```

---

## Debug Endpoints

### Verify Nomba Webhook Routing
```http
GET /v1/debug/nomba/verify-webhook-routing
```

**Response (success):**
```json
{
  "status": "success",
  "message": "Webhook routing verified successfully",
  "account_holder_id": "acc_xxx",
  "webhook_configured": true
}
```

**Response (error - not configured):**
```json
{
  "status": "error",
  "message": "Webhook is not properly configured",
  "account_holder_id": "acc_xxx",
  "webhook_configured": false,
  "action_required": true,
  "instructions": "IMPORTANT: Webhook is not properly configured!\n\n1. Go to Nomba Dashboard..."
}
```

---

## Error Responses

All errors follow this format:
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message"
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_OTP` | 400 | OTP is invalid or expired |
| `OTP_EXPIRED` | 400 | OTP has expired |
| `USER_NOT_FOUND` | 404 | User does not exist |
| `INVALID_PIN` | 401 | PIN verification failed |
| `VERIFICATION_REQUIRED` | 403 | KYC verification required |
| `INSUFFICIENT_BALANCE` | 400 | Not enough funds |
| `INVALID_SIGNATURE` | 400 | Transaction signature invalid |
| `DUPLICATE_NONCE` | 400 | Transaction already processed |
| `TOKEN_EXPIRED` | 401 | Offline token has expired |

---

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `/auth/register` | 5/minute/IP |
| `/auth/login` | 10/minute/IP |
| `/auth/pin/verify` | 5/15min/user |
| `/transactions/sync` | 100/minute/user |

---

## Testing Checklist

### Pre-Production
- [ ] Configure ENCRYPTION_KEY
- [ ] Configure SMS provider (Termii)
- [ ] Configure Nomba API credentials
- [ ] Verify webhook routing via `/v1/debug/nomba/verify-webhook-routing`
- [ ] Test complete user flow
- [ ] Test KYC flow
- [ ] Test offline payment flow

### Production Checklist
- [ ] Use real Nomba credentials
- [ ] Use real SMS API key
- [ ] Use real Dojah/Smile Identity credentials
- [ ] Enable webhook URL in Nomba dashboard
- [ ] Set correct accountHolderId in webhook registration
