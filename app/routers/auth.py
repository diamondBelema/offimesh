"""Authentication-related API routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.middleware.auth import CurrentUser, get_current_user
from app.middleware.correlation_id import get_correlation_id
from app.schemas import (
    CreatePINRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    VerifyOTPRequest,
    VerifyPINRequest,
    ok_response,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


@router.post("/register")
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_session),
):
    """Register a new user account."""
    correlation_id = get_correlation_id(request)
    service = AuthService(db)
    result = await service.register(
        phone=body.phone,
        name=body.name,
        role=body.role,
        correlation_id=correlation_id,
    )
    return ok_response(result, correlation_id)


@router.post("/verify-otp")
async def verify_otp(
    request: Request,
    body: VerifyOTPRequest,
    db: AsyncSession = Depends(get_session),
):
    """Verify OTP to activate account."""
    correlation_id = get_correlation_id(request)
    service = AuthService(db)
    result = await service.verify_otp(
        user_id=body.user_id,
        otp=body.otp,
        correlation_id=correlation_id,
    )
    return ok_response(result, correlation_id)


@router.post("/login")
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_session),
):
    """Initiate login by sending OTP."""
    correlation_id = get_correlation_id(request)
    service = AuthService(db)
    result = await service.login(
        phone=body.phone,
        correlation_id=correlation_id,
    )
    return ok_response(result, correlation_id)


@router.post("/token")
async def get_token(
    request: Request,
    body: dict,
    db: AsyncSession = Depends(get_session),
):
    """Verify login OTP and get access token."""
    correlation_id = get_correlation_id(request)
    service = AuthService(db)
    result = await service.verify_login(
        user_id=body.get("user_id", ""),
        otp=body.get("otp", ""),
        correlation_id=correlation_id,
    )
    return ok_response(result, correlation_id)


@router.post("/refresh")
async def refresh_token(
    request: Request,
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_session),
):
    """Refresh access token."""
    correlation_id = get_correlation_id(request)
    service = AuthService(db)
    result = await service.refresh_tokens(body.refresh_token)
    return ok_response(result, correlation_id)


@router.post("/pin/create")
async def create_pin(
    request: Request,
    body: CreatePINRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Create transaction PIN."""
    correlation_id = get_correlation_id(request)
    service = AuthService(db)
    result = await service.set_pin(
        user_id=str(user.id),
        pin=body.pin,
        correlation_id=correlation_id,
    )
    return ok_response(result, correlation_id)


@router.post("/pin/verify")
async def verify_pin(
    request: Request,
    body: VerifyPINRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    Verify transaction PIN.

    RATE LIMITED: 5 attempts per 15 minutes.
    Invalid attempts are tracked to prevent brute force.
    """
    correlation_id = get_correlation_id(request)
    service = AuthService(db)
    result = await service.verify_pin(
        user_id=str(user.id),
        pin=body.pin,
        correlation_id=correlation_id,
    )
    return ok_response(result, correlation_id)
