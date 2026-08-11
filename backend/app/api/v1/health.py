"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Provides runtime health checks for database, Redis, and external provider telemetry.
- Merges computed and cached provider state without hiding disconnected or fallback status.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.db import get_db
from app.core.config import settings
from app.core.redis_client import redis_bus
import json
import time

router = APIRouter()

@router.get("")
async def health_root():
    """Simple root health endpoint for audit script."""
    return {"status": "healthy", "timestamp": time.time()}


def _is_sqlite() -> bool:
    """Return True when the active DATABASE_URL points at SQLite."""
    return "sqlite" in settings.DATABASE_URL.lower()


async def _check_schema_postgres(db: AsyncSession) -> dict:
    """
    Check required schema columns through PostgreSQL information_schema.

    The route uses this in non-SQLite deployments to keep health reporting
    driver-aware while validating the same table/column contract.
    """
    integrity_checks = {
        "recommendations": ["portfolio_id", "ingest_ts"],
        "execution_logs": ["action", "signal_id"]
    }
    report = {}
    for table, cols in integrity_checks.items():
        for col in cols:
            check_sql = (
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table}' AND column_name = '{col}'"
            )
            res = await db.execute(text(check_sql))
            exists = res.scalar() is not None
            report[f"{table}.{col}"] = "EXISTS" if exists else "MISSING"
    return report


async def _check_schema_sqlite(db: AsyncSession) -> dict:
    """
    Check required schema columns through SQLite PRAGMA metadata.

    This path supports local validation runs where PostgreSQL system catalogs
    are unavailable but the API still needs schema integrity reporting.
    """
    integrity_checks = {
        "recommendations": ["portfolio_id", "ingest_ts"],
        "execution_logs": ["action", "signal_id"]
    }
    report = {}
    for table, cols in integrity_checks.items():
        pragma_res = await db.execute(text(f"PRAGMA table_info({table})"))
        existing_cols = {row[1] for row in pragma_res.fetchall()}
        for col in cols:
            report[f"{table}.{col}"] = "EXISTS" if col in existing_cols else "MISSING"
    return report


@router.get("/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    """
    Check database connectivity and schema integrity.

    Note: Schema checks use PRAGMA table_info for SQLite and information_schema
    for PostgreSQL. Both paths verify the same column requirements.
    """
    start = time.perf_counter()
    try:
        # Connectivity check (works on both SQLite and PostgreSQL)
        await db.execute(text("SELECT 1"))

        # Schema integrity check — driver-aware
        if _is_sqlite():
            report = await _check_schema_sqlite(db)
            db_driver = "sqlite"
        else:
            report = await _check_schema_postgres(db)
            db_driver = "postgresql"

        latency = (time.perf_counter() - start) * 1000
        overall_integrity = "PASS" if all(v == "EXISTS" for v in report.values()) else "FAIL"

        return {
            "status": "healthy" if overall_integrity == "PASS" else "degraded",
            "latency_ms": round(latency, 2),
            "integrity": overall_integrity,
            "db_driver": db_driver,
            "report": report
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@router.get("/redis")
async def health_redis():
    """Check Redis connectivity and return a basic latency measurement."""
    start = time.perf_counter()
    try:
        await redis_bus.connect()
        await redis_bus.client.ping()
        latency = (time.perf_counter() - start) * 1000
        return {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@router.get("/full")
async def health_full(db: AsyncSession = Depends(get_db)):
    """Return combined database and Redis health for top-level monitoring."""
    db_res = await health_db(db)
    redis_res = await health_redis()

    overall = (
        "healthy"
        if db_res["status"] == "healthy" and redis_res["status"] == "healthy"
        else "degraded"
    )

    return {
        "status": overall,
        "database": db_res,
        "redis": redis_res,
        "timestamp": time.time()
    }

async def _cached_source_health(cache_key: str):
    """Read provider health from Redis so multi-worker API responses stay consistent."""
    try:
        await redis_bus.connect()
        raw = await redis_bus.get(cache_key)
        if not raw:
            return None

        cached = json.loads(raw)
        if isinstance(cached, dict) and cached:
            return cached
    except Exception:
        return None

    return None

def _merge_fresher_health(computed: dict, cached: dict) -> dict:
    """
    Merge computed and cached provider health without hiding stale providers.

    In multi-worker deployments the API process may not own ingestion, so Redis
    health can be fresher. Disconnected/error rows are still preserved.
    """
    merged = dict(computed or {})
    for provider_id, cached_status in (cached or {}).items():
        current_status = merged.get(provider_id, {})
        try:
            cached_ts = float(
                cached_status.get("last_ingest_ts")
                or cached_status.get("last_success_at")
                or 0.0
            )
        except Exception:
            cached_ts = 0.0
        try:
            current_ts = float(
                current_status.get("last_ingest_ts")
                or current_status.get("last_success_at")
                or 0.0
            )
        except Exception:
            current_ts = 0.0

        current_connected = bool(current_status.get("connected"))
        cached_connected = bool(cached_status.get("connected"))
        if cached_ts > current_ts or (cached_connected and not current_connected):
            merged[provider_id] = cached_status
    return merged

@router.get("/providers/health")
async def health_providers():
    """
    Return standardized health status for market, news, and broker providers.

    Provider rows report connected/disconnected/rate-limited/fallback state with
    latency and last heartbeat metadata, while avoiding any credential exposure.
    """
    from app.services.ingestion.market_ingester import market_ingester
    from app.services.ingestion.news_ingester import news_ingester
    from app.services.broker.alpaca_adapter import alpaca_adapter
    
    # Market provider health is computed from local Redis/DB signals, then
    # merged with cached worker health when another process owns ingestion.
    try:
        market_health = await market_ingester.get_source_health()
    except Exception:
        market_health = {}
    market_health = _merge_fresher_health(
        market_health,
        await _cached_source_health("market:source_health") or {},
    )
    
    # News health follows the same merge pattern as market data so restarted API
    # workers can still show recent provider heartbeats.
    try:
        news_health = await news_ingester.get_source_health()
    except Exception:
        news_health = {}
    news_health = _merge_fresher_health(
        news_health,
        await _cached_source_health("news:source_health") or {},
    )
    
    # Execution provider health verifies Alpaca Paper only in PAPER mode. Other
    # modes are labeled fallback instead of connected external brokerage.
    alpaca_status = "DISCONNECTED"
    alpaca_connected = False
    alpaca_latency_ms = 0
    alpaca_last_ts = 0.0
    try:
        if settings.TRADING_MODE == "PAPER":
            start = time.perf_counter()
            await alpaca_adapter.get_account()
            alpaca_latency_ms = int((time.perf_counter() - start) * 1000)
            alpaca_last_ts = time.time()
            alpaca_status = "CONNECTED"
            alpaca_connected = True
        else:
            alpaca_status = "INTERNAL_FALLBACK"
            alpaca_connected = True
            alpaca_last_ts = time.time()
    except Exception as e:
        err_str = str(e).upper()
        if "401" in err_str or "UNAUTHORIZED" in err_str:
            alpaca_status = "AUTH_FAILED"
        elif "403" in err_str:
            alpaca_status = "FORBIDDEN"
        elif "429" in err_str:
            alpaca_status = "RATE_LIMITED"
        else:
            alpaca_status = "DISCONNECTED"
        alpaca_connected = False

    # Reliability labels distinguish healthy, stale, fallback, and hard errors
    # without exposing credentials or treating fallback as an external link.
    alpaca_reliability = "HEALTHY"
    if alpaca_status in ["AUTH_FAILED", "FORBIDDEN", "RATE_LIMITED"]:
        alpaca_reliability = "ERROR"
    elif alpaca_status == "INTERNAL_FALLBACK":
        alpaca_reliability = "FALLBACK"
        alpaca_connected = False # Stricter: Fallback is NOT connected
    elif alpaca_status == "DISCONNECTED" or not alpaca_connected:
        alpaca_reliability = "STALE"

    return {
        "market_providers": market_health,
        "news_providers": news_health,
        "execution_providers": {
            "alpaca": {
                "status": alpaca_status,
                "label": alpaca_status,
                "connected": alpaca_connected,
                "mode": settings.TRADING_MODE,
                "reliability": alpaca_reliability,
                "stale": not alpaca_connected and alpaca_status != "INTERNAL_FALLBACK",
                "latency_ms": alpaca_latency_ms,
                "last_success_at": alpaca_last_ts,
                "last_ingest_ts": alpaca_last_ts
            }
        },
        "timestamp": time.time()
    }
