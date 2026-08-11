"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Project source/configuration file supporting the APEX AI Portfolio Management System.
"""
import os
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# 🛡️ Graduation Verification: Load environment variables from .env if present.
load_dotenv()

# Test-only secrets keep the public application configuration strict while
# allowing isolated test imports without a developer .env file.
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-never-use-in-production")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 🛡️ Graduation Verification: Honor environment variables for Docker compatibility.
db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./apex_test.db")
os.environ["DATABASE_URL"] = db_url

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
os.environ["REDIS_URL"] = redis_url

os.environ["LIVE_VERIFY_MODE"] = "True"

import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.config import settings
from app.core.redis_client import redis_bus
from app.core.db import init_models

logger = logging.getLogger("PytestSetup")
_infra_seeded = False

@pytest.fixture(autouse=True)
async def setup_infra():
    """Ensure Redis and DB are connected for each test with retry logic for stability."""
    global _infra_seeded
    success = False
    last_err = None
    for i in range(5):
        try:
            await redis_bus.connect()
            await init_models()
            if not _infra_seeded:
                from app.core.seed import seed_database
                await seed_database()
                _infra_seeded = True
            success = True
            break
        except Exception as e:
            last_err = e
            logger.warning(f"Infra setup attempt {i+1} failed: {e}. Retrying in 2s...")
            await asyncio.sleep(2)
    
    if not success:
        raise RuntimeError(f"STRICT_FAIL: Could not initialize test infrastructure after 5 attempts: {last_err}")
    yield

@pytest.fixture
async def controlled_client():
    """A client fixture for testing the API endpoints with lifespan support."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

@pytest.fixture
def controlled_db_session():
    """A database session fixture for testing."""
    from app.core.db import AsyncSessionLocal
    return AsyncSessionLocal
