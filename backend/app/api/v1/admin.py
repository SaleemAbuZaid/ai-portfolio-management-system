"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Provides admin-only summary, role request, and system-control endpoints.
- Supports the Admin Console without exposing secrets or changing provider behavior.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from app.core.db import AsyncSessionLocal, get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.all_models import User, Portfolio, ExecutionLog
from app.services.ingestion.market_ingester import market_ingester
from app.core.config import get_settings
from app.api.v1.auth import check_role, get_current_user
from app.models.schemas.auth_schemas import UserOut
from datetime import datetime, timezone
from typing import List

router = APIRouter(dependencies=[Depends(check_role(["ADMIN"]))])
settings = get_settings()

@router.get("/summary")
async def get_admin_summary(db: AsyncSession = Depends(get_db)):
    """
    Return a high-level system overview for the Admin Console.

    Counts are read from the active database session and broker status is reduced
    to a safe connection label for academic demonstration.
    """
    # Role counts support the Admin Console governance overview.
    res = await db.execute(select(func.count(User.id)))
    user_count = res.scalar()
    
    res = await db.execute(select(func.count(User.id)).where(User.role == "ADMIN"))
    admin_count = res.scalar()
    
    res = await db.execute(select(func.count(User.id)).where(User.role == "BROKER"))
    broker_count = res.scalar()
    
    res = await db.execute(select(func.count(User.id)).where(User.role == "USER"))
    normal_user_count = res.scalar()

    # Model portfolio count, separate from Alpaca Paper account status.
    res = await db.execute(select(func.count(Portfolio.id)))
    portfolio_count = res.scalar()

    # Execution logs are used by audit panels and proof checks.
    res = await db.execute(select(func.count(ExecutionLog.id)))
    exec_count = res.scalar()

    # Broker status is reduced to a safe label; credential values are not exposed.
    alpaca_status = "CONNECTED" if settings.ALPACA_API_KEY else "DISCONNECTED"
    if settings.TRADING_MODE != "PAPER":
        alpaca_status = "STUB_MODE"

    # Maintenance mode is stored in Redis so all API workers see the same flag.
    from app.core.redis_client import redis_bus
    await redis_bus.connect()
    m_raw = await redis_bus.get("system:maintenance_mode")
    m_mode = "ON" if m_raw == b"ON" else "OFF"

    return {
        "users_count": user_count,
        "admin_count": admin_count,
        "broker_count": broker_count,
        "normal_user_count": normal_user_count,
        "portfolios_count": portfolio_count,
        "execution_logs_count": exec_count,
        "alpaca_status": alpaca_status,
        "provider_health": await market_ingester.get_source_health(),
        "system_audit_status": "PASS",
        "maintenance_mode": m_mode,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@router.get("/users", response_model=List[UserOut])
async def get_admin_users(db: AsyncSession = Depends(get_db)):
    """Return all dashboard users for administrator review."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()

@router.get("/role-requests")
async def get_role_requests(db: AsyncSession = Depends(get_db)):
    """Return pending broker-role requests for Admin Console approval."""
    result = await db.execute(
        select(User).where(User.approval_status == "PENDING", User.requested_role == "BROKER")
    )
    return result.scalars().all()

@router.post("/role-requests/{user_id}/approve")
async def approve_role_request(user_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Approve one pending broker-role request.

    The approving admin id and timestamp are stored for governance auditing.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.approval_status != "PENDING":
        raise HTTPException(status_code=400, detail="Request is not pending")
        
    user.role = "BROKER"
    user.approval_status = "APPROVED"
    user.approved_by = current_user.id
    user.approved_at = datetime.now(timezone.utc)
    
    await db.commit()
    return {"message": "Broker request approved", "status": "APPROVED", "role": "BROKER"}

@router.post("/role-requests/{user_id}/reject")
async def reject_role_request(user_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Reject one pending broker-role request and record the admin reviewer."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.approval_status != "PENDING":
        raise HTTPException(status_code=400, detail="Request is not pending")
        
    user.approval_status = "REJECTED"
    user.approved_by = current_user.id
    user.approved_at = datetime.now(timezone.utc)
    
    await db.commit()
    return {"message": "Broker request rejected", "status": "REJECTED"}

@router.post("/maintenance/enable")
async def enable_maintenance():
    """Enable the Redis-backed maintenance flag for all API workers."""
    from app.core.redis_client import redis_bus
    await redis_bus.connect()
    await redis_bus.set("system:maintenance_mode", "ON")
    return {"status": "SUCCESS", "maintenance_mode": "ON"}

@router.post("/maintenance/disable")
async def disable_maintenance():
    """Disable the Redis-backed maintenance flag for all API workers."""
    from app.core.redis_client import redis_bus
    await redis_bus.connect()
    await redis_bus.set("system:maintenance_mode", "OFF")
    return {"status": "SUCCESS", "maintenance_mode": "OFF"}

@router.get("/maintenance/status")
async def get_maintenance_status():
    """Return the current Redis-backed maintenance mode state."""
    from app.core.redis_client import redis_bus
    await redis_bus.connect()
    current = await redis_bus.get("system:maintenance_mode")
    state = "ON" if current == b"ON" else "OFF"
    return {"status": "SUCCESS", "maintenance_mode": state}

@router.post("/maintenance/toggle")
async def toggle_maintenance():
    """Toggle system-wide maintenance mode via Redis flag."""
    from app.core.redis_client import redis_bus
    await redis_bus.connect()
    
    current = await redis_bus.get("system:maintenance_mode")
    new_state = "ON" if current != b"ON" else "OFF"
    await redis_bus.set("system:maintenance_mode", new_state)
    
    return {"status": "SUCCESS", "maintenance_mode": new_state}

@router.post("/cache/flush")
async def flush_system_cache():
    """
    Flush app-specific market, news, and performance cache keys.

    Session/authentication keys are intentionally excluded from this admin action.
    """
    from app.core.redis_client import redis_bus
    await redis_bus.connect()
    
    # Selective flush avoids breaking session state.
    keys = await redis_bus.keys("market:*") + await redis_bus.keys("news:*") + await redis_bus.keys("perf:*")
    if keys:
        await redis_bus.delete(*keys)
    
    return {"status": "SUCCESS", "flushed_keys": len(keys)}
