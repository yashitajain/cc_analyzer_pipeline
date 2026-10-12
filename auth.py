"""
Authentication: JWT token generation/validation and password hashing.
"""

import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from config import settings
from typing import Optional


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


# JWT token handling
def create_jwt_token(data: dict, expires_in_hours: Optional[int] = None) -> str:
    """
    Create a JWT token.

    Args:
        data: dict to encode (e.g., {"user_id": 1, "username": "yashu"})
        expires_in_hours: hours until expiration (default from settings)

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    # Set expiration
    if expires_in_hours is None:
        expires_in_hours = settings.JWT_EXPIRATION_HOURS

    expire = datetime.utcnow() + timedelta(hours=expires_in_hours)
    to_encode.update({"exp": expire})

    # Encode
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt


def decode_jwt_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string (with or without "Bearer " prefix)

    Returns:
        Decoded payload dict, or None if invalid/expired
    """
    # Remove "Bearer " prefix if present
    if token.startswith("Bearer "):
        token = token[7:]

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        print("Token expired")
        return None
    except jwt.InvalidTokenError:
        print("Invalid token")
        return None
