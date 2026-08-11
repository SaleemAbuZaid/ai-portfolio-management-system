"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Contains password hashing and JWT helpers used by authentication routes.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Union
import jwt
from jwt.exceptions import PyJWTError as JWTError
from passlib.context import CryptContext
from app.core.config import settings
from loguru import logger

# PBKDF2 avoids external C dependencies and runs reliably in Docker/Alpine
# validation environments while still storing only password hashes.

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
    pbkdf2_sha256__default_rounds=600000
)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a submitted password against the stored password hash."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False

def get_password_hash(password: str) -> str:
    """Hash a plain password before database persistence."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed JWT access token for authenticated API requests.

    The payload is copied, given an expiration, and signed with the configured
    secret; raw passwords or credential values are never included.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT access token, returning None on failure."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError as e:
        logger.error(f"JWT Decode Error: {e}")
        return None
