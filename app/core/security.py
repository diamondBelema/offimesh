"""Security utilities: password hashing, JWT, encryption."""
from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# --- Password Hashing ---

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash password using Argon2."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return pwd_context.verify(plain_password, hashed_password)


# --- Phone Number Hashing (Scrypt with per-user salt) ---


def hash_phone(phone: str, salt: str | None = None) -> tuple[str, str]:
    """
    Hash phone number with scrypt and per-user salt.
    Returns (hash, salt) - salt must be stored.
    """
    if salt is None:
        salt = secrets.token_hex(16)

    # Use scrypt for phone hashing (more secure than SHA-256)
    key = hashlib.scrypt(
        phone.encode(),
        salt=salt.encode(),
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    phone_hash = key.hex()
    return phone_hash, salt


def verify_phone_hash(phone: str, stored_hash: str, salt: str) -> bool:
    """Verify phone number against stored hash."""
    computed_hash, _ = hash_phone(phone, salt)
    return secrets.compare_digest(computed_hash, stored_hash)


# --- AES-256-GCM Encryption for Sensitive Data ---


def _get_encryption_key() -> bytes:
    """Derive encryption key from JWT secret."""
    # Use a fixed derivation for simplicity - in production use a separate key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"offimesh_encryption_salt",
        iterations=100000,
    )
    return base64.urlsafe_b64encode(
        kdf.derive(settings.jwt_private_key.encode()[:32].ljust(32, b"0"))
    )


def encrypt_value(plaintext: str) -> str:
    """Encrypt sensitive value using Fernet (AES-128-CBC with HMAC)."""
    key = _get_encryption_key()
    f = Fernet(key)
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt sensitive value."""
    key = _get_encryption_key()
    f = Fernet(key)
    return f.decrypt(ciphertext.encode()).decode()


# --- JWT Token Management ---


def create_access_token(
    subject: str,
    device_id: str,
    role: str,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Create JWT access token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_access_ttl_minutes)

    claims = {
        "sub": subject,
        "device_id": device_id,
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if additional_claims:
        claims.update(additional_claims)

    return jwt.encode(
        claims,
        settings.jwt_private_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    subject: str,
    device_id: str,
    token_family: str,
) -> str:
    """Create JWT refresh token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.jwt_refresh_ttl_days)

    claims = {
        "sub": subject,
        "device_id": device_id,
        "family": token_family,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(
        claims,
        settings.jwt_private_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as e:
        raise InvalidTokenError(f"Invalid token: {e}") from e


class InvalidTokenError(Exception):
    """Raised when token is invalid or expired."""
    pass


# --- PIN Management ---


def hash_pin(pin: str) -> str:
    """Hash transaction PIN using Argon2."""
    return hash_password(pin)


def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    """Verify transaction PIN."""
    return verify_password(plain_pin, hashed_pin)


# --- Nonce Generation ---


def generate_nonce(length: int = 32) -> str:
    """Generate cryptographically secure random nonce."""
    return secrets.token_hex(length)


# --- Signature Verification Helpers ---


def constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return secrets.compare_digest(a, b)
