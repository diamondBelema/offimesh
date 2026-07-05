"""Pydantic schemas for OffiMesh API."""
from app.schemas.base import (
    ApiResponse,
    BaseSchema,
    ErrorDetail,
    PaginatedResponse,
    ResponseMeta,
    error_response,
    ok_response,
)
from app.schemas.auth import (
    CreatePINRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserBalanceResponse,
    UserLimitsResponse,
    UserResponse,
    VerifyOTPRequest,
    VerifyPINRequest,
)
from app.schemas.device import (
    DeviceListResponse,
    DeviceRegisterRequest,
    DeviceResponse,
)
from app.schemas.token import (
    ActiveTokenResponse,
    OfflineTokenResponse,
    ProvisionTokenRequest,
    TokenListResponse,
)
from app.schemas.transaction import (
    SingleTransactionData,
    TransactionListResponse,
    TransactionResponse,
    TransactionResult,
    TransactionSyncRequest,
    TransactionSyncResponse,
)
from app.schemas.settlement import (
    SettlementListResponse,
    SettlementProcessResponse,
    SettlementResponse,
)
from app.schemas.wallet import (
    FundWalletRequest,
    FundingStatusResponse,
    VirtualAccountResponse,
    WalletBalanceResponse,
)
from app.schemas.bvn import (
    BVNInitiateResponse,
    BVNStatusResponse,
    ConfirmBVNRequest,
    InitiateBVNRequest,
)
from app.schemas.webhook import (
    NombaWebhookPayload,
    TransferFailedData,
    TransferSuccessData,
    VirtualAccountFundedData,
    WebhookEventResponse,
)
from app.schemas.health import (
    DetailedHealthResponse,
    HealthResponse,
    RootResponse,
)
from app.schemas.identity import (
    CanProvisionTokenResponse,
    DeviceTrustPayloadSchema,
    FraudAssessmentResponse,
    InitiateVerificationRequest,
    InitiateVerificationResponse,
    TrustEvaluationResponse,
    VerificationDetail,
    VerificationStatusResponse,
    VerifyFaceRequest,
    VerifyFaceResponse,
)

__all__ = [
    # Base
    "BaseSchema",
    "ResponseMeta",
    "ErrorDetail",
    "ApiResponse",
    "PaginatedResponse",
    "ok_response",
    "error_response",
    # Auth
    "RegisterRequest",
    "VerifyOTPRequest",
    "LoginRequest",
    "RefreshTokenRequest",
    "CreatePINRequest",
    "VerifyPINRequest",
    "RegisterResponse",
    "TokenResponse",
    "UserResponse",
    "UserBalanceResponse",
    "UserLimitsResponse",
    # Device
    "DeviceRegisterRequest",
    "DeviceResponse",
    "DeviceListResponse",
    # Token
    "ProvisionTokenRequest",
    "OfflineTokenResponse",
    "ActiveTokenResponse",
    "TokenListResponse",
    # Transaction
    "TransactionSyncRequest",
    "SingleTransactionData",
    "TransactionSyncResponse",
    "TransactionResult",
    "TransactionResponse",
    "TransactionListResponse",
    # Settlement
    "SettlementResponse",
    "SettlementListResponse",
    "SettlementProcessResponse",
    # Wallet
    "FundWalletRequest",
    "VirtualAccountResponse",
    "WalletBalanceResponse",
    "FundingStatusResponse",
    # BVN
    "InitiateBVNRequest",
    "ConfirmBVNRequest",
    "BVNInitiateResponse",
    "BVNStatusResponse",
    # Webhook
    "NombaWebhookPayload",
    "VirtualAccountFundedData",
    "TransferSuccessData",
    "TransferFailedData",
    "WebhookEventResponse",
    # Health
    "HealthResponse",
    "DetailedHealthResponse",
    "RootResponse",
    # Identity
    "InitiateVerificationRequest",
    "InitiateVerificationResponse",
    "VerifyFaceRequest",
    "VerifyFaceResponse",
    "VerificationStatusResponse",
    "VerificationDetail",
    "CanProvisionTokenResponse",
    "DeviceTrustPayloadSchema",
    "TrustEvaluationResponse",
    "FraudAssessmentResponse",
]
