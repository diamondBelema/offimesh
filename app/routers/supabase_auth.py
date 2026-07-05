"""Supabase authentication API routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.middleware.auth import CurrentUser, get_current_user
from app.middleware.correlation_id import get_correlation_id
from app.schemas.base import BaseSchema, ok_response
from app.schemas import ok_response
from app.services.supabase_service import (
    create_supabase_user,
    sign_in_with_password,
    refresh_supabase_session,
    verify_supabase_jwt,
    sign_out_supabase_user,
)

router = APIRouter(prefix="/v1/auth/supabase", tags=["Supabase Auth"])


class SupabaseSignUpRequest(BaseSchema):
    """Sign up request with email and password."""

    email: str
    password: str
    name: str | None = None


class SupabaseSignInRequest(BaseSchema):
    """Sign in request with email and password."""

    email: str
    password: str


class SupabaseRefreshRequest(BaseSchema):
    """Refresh token request."""

    refresh_token: str


class SupabaseTokenVerifyRequest(BaseSchema):
    """Token verification request."""

    token: str


class SupabaseAuthResponse(BaseSchema):
    """Authentication response."""

    access_token: str
    refresh_token: str
    user: dict | None = None


@router.post("/signup")
async def sign_up(
    request: Request,
    body: SupabaseSignUpRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    Create a new user account with Supabase Auth.

    Uses email/password authentication (email confirmation disabled).
    """
    correlation_id = get_correlation_id(request)

    user_metadata = None
    if body.name:
        user_metadata = {"full_name": body.name}

    user = await create_supabase_user(
        email=body.email,
        password=body.password,
        user_metadata=user_metadata,
    )

    return ok_response({
        "user_id": user.get("id"),
        "email": user.get("email"),
        "message": "Account created successfully",
    }, correlation_id)


@router.post("/signin")
async def sign_in(
    request: Request,
    body: SupabaseSignInRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    Sign in with email and password.

    Returns access token and refresh token.
    """
    correlation_id = get_correlation_id(request)

    session = await sign_in_with_password(
        email=body.email,
        password=body.password,
    )

    return ok_response(
        SupabaseAuthResponse(
            access_token=session["access_token"],
            refresh_token=session["refresh_token"],
            user=session.get("user"),
        ),
        correlation_id,
    )


@router.post("/refresh")
async def refresh_token(
    request: Request,
    body: SupabaseRefreshRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    Refresh an access token using a refresh token.
    """
    correlation_id = get_correlation_id(request)

    session = await refresh_supabase_session(body.refresh_token)

    return ok_response(
        SupabaseAuthResponse(
            access_token=session["access_token"],
            refresh_token=session["refresh_token"],
        ),
        correlation_id,
    )


@router.post("/verify")
async def verify_token(
    request: Request,
    body: SupabaseTokenVerifyRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    Verify a Supabase JWT token.

    Returns the token payload if valid.
    """
    correlation_id = get_correlation_id(request)

    payload = await verify_supabase_jwt(body.token)

    return ok_response({
        "valid": True,
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "expires_at": payload.get("exp"),
    }, correlation_id)


@router.post("/signout")
async def sign_out(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    Sign out the current user.

    Invalidates their session.
    """
    correlation_id = get_correlation_id(request)

    # Get the Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header[7:]
        await sign_out_supabase_user(access_token)

    return ok_response({
        "message": "Signed out successfully",
    }, correlation_id)
