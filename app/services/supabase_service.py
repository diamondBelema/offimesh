"""Supabase client configuration for auth and notifications."""
from __future__ import annotations

import structlog
from supabase import create_client, Client
from typing import Optional

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Singleton clients
_supabase_client: Optional[Client] = None
_supabase_admin_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Get Supabase client with anon key (for user-facing operations).

    Use this for:
    - User authentication
    - Real-time subscriptions
    - RLS-protected queries
    """
    global _supabase_client
    if _supabase_client is None:
        if not settings.supabase_url or not settings.supabase_anon_key:
            logger.warning("supabase_not_configured")
            raise RuntimeError("Supabase URL and anon key must be configured")

        _supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_anon_key,
        )
        logger.info("supabase_client_initialized")

    return _supabase_client


def get_supabase_admin_client() -> Client:
    """
    Get Supabase client with service role key (for admin operations).

    Use this for:
    - Server-side operations that bypass RLS
    - Admin user management
    - Sending notifications
    - Background tasks

    WARNING: This client bypasses RLS. Use with caution.
    """
    global _supabase_admin_client
    if _supabase_admin_client is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            logger.warning("supabase_admin_not_configured")
            raise RuntimeError("Supabase URL and service role key must be configured")

        _supabase_admin_client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        logger.info("supabase_admin_client_initialized")

    return _supabase_admin_client


async def verify_supabase_jwt(token: str) -> dict:
    """
    Verify a Supabase JWT token and return the payload.

    Args:
        token: The JWT token to verify

    Returns:
        dict with user claims

    Raises:
        AuthenticationError if token is invalid
    """
    from app.core.exceptions import AuthenticationError
    import jwt

    if not settings.supabase_jwt_secret:
        raise AuthenticationError("Supabase JWT secret not configured")

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(f"Invalid token: {str(e)}")


async def get_user_by_supabase_id(supabase_user_id: str) -> dict | None:
    """
    Get user profile from Supabase auth by ID.

    Args:
        supabase_user_id: The Supabase auth user ID

    Returns:
        User dict or None
    """
    client = get_supabase_admin_client()
    try:
        response = client.auth.admin.get_user_by_id(supabase_user_id)
        return response.user.model_dump() if response.user else None
    except Exception as e:
        logger.error("supabase_get_user_failed", error=str(e))
        return None


async def create_supabase_user(
    email: str,
    password: str,
    user_metadata: dict | None = None,
) -> dict:
    """
    Create a new user in Supabase Auth.

    Args:
        email: User email
        password: User password
        user_metadata: Optional metadata to attach to user

    Returns:
        Created user dict
    """
    from app.core.exceptions import ConflictError

    client = get_supabase_admin_client()
    try:
        response = client.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": False,  # Disable email confirmation
            "user_metadata": user_metadata or {},
        })
        return response.user.model_dump()
    except Exception as e:
        if "already registered" in str(e).lower():
            raise ConflictError("User already registered with this email")
        raise


async def sign_in_with_password(email: str, password: str) -> dict:
    """
    Sign in user with email and password.

    Args:
        email: User email
        password: User password

    Returns:
        Session dict with access_token, refresh_token
    """
    from app.core.exceptions import AuthenticationError

    client = get_supabase_client()
    try:
        response = client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user": response.user.model_dump(),
        }
    except Exception as e:
        logger.warning("supabase_sign_in_failed", error=str(e))
        raise AuthenticationError(f"Sign in failed: {str(e)}")


async def refresh_supabase_session(refresh_token: str) -> dict:
    """
    Refresh a Supabase session.

    Args:
        refresh_token: The refresh token

    Returns:
        New session dict
    """
    from app.core.exceptions import AuthenticationError

    client = get_supabase_client()
    try:
        response = client.auth.refresh_session({
            "refresh_token": refresh_token,
        })
        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
        }
    except Exception as e:
        raise AuthenticationError(f"Session refresh failed: {str(e)}")


async def sign_out_supabase_user(access_token: str) -> None:
    """
    Sign out a user by invalidating their session.

    Args:
        access_token: The user's access token
    """
    client = get_supabase_admin_client()
    try:
        client.auth.admin.sign_out(access_token)
    except Exception as e:
        logger.warning("supabase_sign_out_failed", error=str(e))
