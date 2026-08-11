"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Provides authenticated profile, password, and avatar endpoints for dashboard users.
- Keeps user-facing account updates separate from role/admin management.
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.api.v1.auth import get_current_user
from app.models.all_models import User
from app.models.schemas.auth_schemas import UserOut, UserProfileUpdate, PasswordChange
from app.core.auth_utils import verify_password, get_password_hash
import os
import shutil
from uuid import uuid4
from loguru import logger

router = APIRouter()

# Avatar uploads are stored under static/ so the React profile panel can render
# them through the same backend origin.
UPLOAD_DIR = os.path.join("static", "uploads", "avatars")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.get("/profile", response_model=UserOut)
async def get_profile(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile for the dashboard panel."""
    return current_user

@router.patch("/profile", response_model=UserOut)
async def update_profile(
    profile_in: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update editable profile fields for the authenticated user.

    UserProfileUpdate only allows safe profile fields, so role/status changes
    remain restricted to admin workflows.
    """
    # UserProfileUpdate schema only allows safe fields.
    # We explicitly only apply those to prevent any accidental role/status promotion.
    if profile_in.full_name is not None:
        current_user.full_name = profile_in.full_name
        
    if profile_in.username is not None and profile_in.username != current_user.username:
        # Check for unique username
        result = await db.execute(select(User).where(User.username == profile_in.username))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Username already taken")
        current_user.username = profile_in.username
        
    if profile_in.gender is not None:
        current_user.gender = profile_in.gender
        
    await db.commit()
    await db.refresh(current_user)
    logger.info(f"User {current_user.id} updated profile.")
    return current_user

@router.post("/profile/change-password")
async def change_password(
    password_in: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Validate the current password and persist a new password hash."""
    if not verify_password(password_in.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    current_user.password_hash = get_password_hash(password_in.new_password)
    await db.commit()
    logger.info(f"User {current_user.id} changed password.")
    return {"status": "success", "message": "Password updated successfully"}

@router.post("/profile/avatar", response_model=UserOut)
async def upload_avatar(
    avatar: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload and persist a profile avatar for the authenticated user.

    The endpoint validates extension and size, stores the file under the static
    avatar directory, and returns the updated user profile.
    """
    filename = avatar.filename or "avatar.png"
    extension = os.path.splitext(filename)[1].lower()
    
    if extension not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="Unsupported image format. Use JPG, PNG or WebP.")

    # We rely on the extension check and size limit for security.
    
    # Validate size before writing to disk.
    avatar.file.seek(0, os.SEEK_END)
    file_size = avatar.file.tell()
    avatar.file.seek(0)
    if file_size > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 2MB.")

    # Include user id and a UUID so uploads do not collide.
    unique_filename = f"avatar_{current_user.id}_{uuid4().hex}{extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    # Save the validated upload to the static avatar directory.
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(avatar.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save avatar: {e}")
        raise HTTPException(status_code=500, detail="Could not save image file.")

    # Store only the public relative URL in the user profile row.
    current_user.avatar_url = f"/static/uploads/avatars/{unique_filename}"
    await db.commit()
    await db.refresh(current_user)
    
    logger.info(f"User {current_user.id} uploaded new avatar.")
    return current_user
