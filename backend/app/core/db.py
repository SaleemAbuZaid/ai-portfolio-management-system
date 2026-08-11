"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Configures the async SQLAlchemy engine, session factory, and database helpers.
- Centralizes session creation so APIs, workers, and tests share the active DATABASE_URL.
"""

import os
import time
import asyncio
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
from app.core.config import settings

logger = logging.getLogger("Database")

# Shared declarative base used by all SQLAlchemy models in the application.
Base = declarative_base()

def get_database_url() -> str:
    """
    Resolve the active async DATABASE_URL for runtime or test mode.

    The helper preserves the configured database target while adapting SQLAlchemy
    driver prefixes for SQLite and PostgreSQL async engines.
    """
    url = settings.DATABASE_URL
    if os.getenv("TEST_MODE") == "1":
        return "sqlite+aiosqlite:///./test_apex.db"
    
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("sqlite"):
        if "aiosqlite" not in url:
            url = url.replace("sqlite:///", "sqlite+aiosqlite:///")
    return url

# Engine and session factory are module-level singletons so API routes and
# workers reuse the same async connection pool within one Python process.
_engine = None
_session_factory = None

def get_engine():
    """
    Return the process-wide async SQLAlchemy engine for the active database URL.

    The engine is recreated when tests or runtime configuration point to a new
    URL, which prevents stale sessions from leaking across validation modes.
    """
    global _engine, _session_factory
    url = get_database_url()
    
    # If engine exists but URL changed (e.g. during test setup), recreate it
    if _engine:
        if str(_engine.url) == url:
            return _engine
        else:
            logger.info(f"Database URL changed to {url}. Recreating engine.")

    # Pool settings keep concurrent API routes and background workers from
    # exhausting connections during dashboard refresh and ingestion bursts.
    pool_config = {
        "pool_pre_ping": True,
        "pool_size": 100,
        "max_overflow": 100,
    }

    if "sqlite" in url:
        # SQLite needs specific connect_args for timeout, but we still apply pooling to prevent 'database is locked'
        _engine = create_async_engine(
            url, 
            connect_args={"check_same_thread": False, "timeout": 60},
            **pool_config
        )
    else:
        _engine = create_async_engine(
            url,
            **pool_config
        )
    
    _session_factory = sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )
    return _engine

def get_session_factory():
    """
    Return the async sessionmaker bound to the current engine.

    Centralizing session construction keeps route handlers, workers, and tests
    on the same database target while allowing the engine to be rebuilt safely.
    """
    if not _session_factory:
        get_engine()
    return _session_factory

def AsyncSessionLocal():
    """
    Create a new AsyncSession for one scoped unit of work.

    Callers should use it with ``async with`` so transactions, connections, and
    ORM state are released after each API request or worker operation.
    """
    return get_session_factory()()

async def get_db():
    """
    FastAPI dependency that yields one request-scoped database session.

    It exists so API routes can use dependency injection while background
    workers can still create sessions directly with ``AsyncSessionLocal``.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def setup_timescaledb():
    """
    Enable TimescaleDB when the configured database is PostgreSQL.

    SQLite validation runs skip this path, while PostgreSQL deployments get the
    time-series extension needed by market history workloads when available.
    """
    url = get_database_url()
    if "postgresql" in url:
        try:
            eng = get_engine()
            async with eng.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
            logger.info("TimescaleDB extension verified.")
        except Exception as e:
            logger.warning(f"TimescaleDB extension not available: {e}")

async def init_models():
    """
    Initialize database tables for the active runtime.

    The startup path imports model definitions, verifies connectivity, creates
    missing tables, and then applies optional PostgreSQL time-series support.
    """
    import app.models.all_models
    try:
        eng = get_engine()
        async with eng.begin() as conn:
            # Simple connectivity check
            if "postgresql" in str(eng.url):
                await conn.execute(text("SELECT 1"))
            await conn.run_sync(Base.metadata.create_all)
            
            logger.info(f"Database initialized successfully at {eng.url}")
        
        await setup_timescaledb()
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        # Fallback logic simplified for clarity
        if "postgresql" in get_database_url():
            logger.warning("Postgres connection failed. Tests may fail if depending on Postgres features.")
            raise
