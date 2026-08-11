"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Handles registration, login, JWT validation, and role-based access dependencies.
- Protects dashboard and broker/admin routes with reusable authentication checks.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta
from app.core.db import get_db
from app.core.config import settings
from app.core.auth_utils import verify_password, get_password_hash, create_access_token, decode_access_token
from app.models.all_models import User
from app.models.schemas.auth_schemas import UserCreate, Token, LoginRequest, UserOut
from loguru import logger

router = APIRouter()
security = HTTPBearer()

async def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Resolve the current authenticated user from a bearer token.

    API routes use this dependency to share one JWT validation path and to reject
    inactive users before any protected dashboard action runs.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token.credentials)
    if payload is None:
        raise credentials_exception
    
    sub = payload.get("sub")
    if sub is None:
        raise credentials_exception
    
    try:
        user_id = int(sub)
    except (ValueError, TypeError):
        raise credentials_exception
        
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    return user

def check_role(roles: list[str]):
    """
    Build a FastAPI dependency that enforces role membership.

    Admin and broker endpoints use this wrapper so authorization rules stay
    centralized and easy to audit for the graduation defense.
    """
    async def role_checker(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return user
    return role_checker

@router.post("/register", response_model=Token)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Register a dashboard user and return a JWT access token.

    Public registration always creates a USER role; broker access is stored as a
    pending request for admin approval instead of granting privileges directly.
    """
    # Enforce unique email before creating the account.
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="User with this email already exists"
        )
    
    # Hash the password before persistence; raw passwords are never stored.
    hashed_password = get_password_hash(user_in.password)
    
    requested_role = user_in.requested_role if user_in.requested_role == "BROKER" else None
    approval_status = "PENDING" if requested_role == "BROKER" else None
    
    db_user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        username=user_in.username or user_in.email.split('@')[0],
        password_hash=hashed_password,
        role="USER", # Public registration cannot self-assign privileged roles.
        requested_role=requested_role,
        approval_status=approval_status,
        is_active=True
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    
    access_token = create_access_token(
        data={"sub": str(db_user.id), "role": db_user.role}
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": db_user
    }

@router.post("/login", response_model=Token)
async def login(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate a user and return a JWT access token.

    The token includes user id and role claims so protected dashboard routes can
    enforce session and role checks with shared dependencies.
    """
    result = await db.execute(select(User).where(User.email == login_data.email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role}
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated profile used to bootstrap the React session."""
    return current_user
