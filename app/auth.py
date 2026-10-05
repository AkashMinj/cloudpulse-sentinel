"""
Authentication and authorization module for CloudPulse Sentinel.
Provides JWT token-based authentication with role-based access control.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
import psycopg2

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "cloudpulse-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Security scheme
security = HTTPBearer(auto_error=False)


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate a user and return user data if successful."""
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        query = """
            SELECT id, username, email, hashed_password, full_name, role, is_active
            FROM users
            WHERE username = %s;
        """

        cursor.execute(query, (username,))
        row = cursor.fetchone()

        if not row:
            return None

        user_id, username, email, hashed_password, full_name, role, is_active = row

        if not is_active:
            return None

        if not verify_password(password, hashed_password):
            return None

        return {
            "id": user_id,
            "username": username,
            "email": email,
            "full_name": full_name,
            "role": role,
        }

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.JWTError:
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """
    Get current authenticated user from JWT token.
    Returns None if no token provided (for optional authentication).
    """
    if not credentials:
        return None

    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        return None

    username = payload.get("sub")
    if not username:
        return None

    # Get user from database
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        query = """
            SELECT id, username, email, full_name, role, is_active
            FROM users
            WHERE username = %s;
        """

        cursor.execute(query, (username,))
        row = cursor.fetchone()

        if not row or not row[5]:  # Check is_active
            return None

        return {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "full_name": row[3],
            "role": row[4],
        }

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


async def require_auth(
    current_user: Optional[dict] = Depends(get_current_user)
) -> dict:
    """
    Require authentication for protected endpoints.
    Raises HTTPException if user is not authenticated.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return current_user


def require_role(required_role: str):
    """
    Dependency factory for role-based access control.
    Roles: admin, analyst, developer, read_only
    """
    async def role_checker(current_user: dict = Depends(require_auth)) -> dict:
        role_hierarchy = {
            "admin": 4,
            "analyst": 3,
            "developer": 2,
            "read_only": 1,
        }

        user_level = role_hierarchy.get(current_user.get("role", "read_only"), 0)
        required_level = role_hierarchy.get(required_role, 999)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role}",
            )

        return current_user

    return role_checker
