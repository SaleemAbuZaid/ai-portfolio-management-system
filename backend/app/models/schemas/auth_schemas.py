"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Defines Pydantic request/response schemas for authentication and user profile flows.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    email: str
    full_name: Optional[str] = None
    role: str = "USER"

class UserCreate(UserBase):
    password: str
    username: Optional[str] = None
    requested_role: Optional[str] = None

class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class UserInDBBase(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    username: str
    requested_role: Optional[str] = None
    approval_status: Optional[str] = None
    gender: Optional[str] = None
    avatar_url: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class UserOut(UserInDBBase):
    pass

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

class TokenPayload(BaseModel):
    sub: Optional[int] = None
    role: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    username: Optional[str] = None
    gender: Optional[str] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
