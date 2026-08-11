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
import pytest
import json
import time
from httpx import AsyncClient
from app.core.config import settings
from app.core.redis_client import redis_bus
from app.core.db import AsyncSessionLocal
from app.models.all_models import Asset, Prediction, PriceHistory
from sqlalchemy import select
from datetime import datetime, timezone
from app.main import app

@pytest.mark.asyncio
async def test_validation_mode_isolation_api():
    """
    API LEVEL ISOLATION TEST:
    Assert that if STEP12_VALIDATION_MODE is False, calling the API
    with a Redis fixture present still returns normal reasoning.
    """
    # 1. Force isolation
    original_mode = settings.STEP12_VALIDATION_MODE
    settings.STEP12_VALIDATION_MODE = False
    
    ticker = "AAPL"
    try:
        async with AsyncSessionLocal() as session:
            # Setup baseline data
            asset_res = await session.execute(select(Asset).where(Asset.ticker == ticker))
            asset = asset_res.scalar_one_or_none()
            if not asset:
                asset = Asset(ticker=ticker, name="Apple Inc", asset_class="EQUITY")
                session.add(asset)
                await session.flush()
            
            asset_id = asset.id
            now = datetime.now(timezone.utc)
            
            # Ensure price exists
            session.add(PriceHistory(asset_id=asset_id, price=150.0, timestamp=now))
            # Ensure prediction exists
            session.add(Prediction(asset_id=asset_id, target_price=155.0, timestamp=now))
            await session.commit()

        # 2. Inject Rogure Fixture
        fixture_key = f"fixture:{ticker.upper()}"
        fixture_data = {
            "sentiment": 0.99,
            "forecast": 0.09,
            "ts": time.time()
        }
        await redis_bus.set(fixture_key, json.dumps(fixture_data), ex=30)
        
        # 3. Call API
        from httpx import ASGITransport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/v1/ai/recommend", json={"ticker": ticker})

            
        assert response.status_code == 200
        data = response.json()
        rec = data["recommendation"]
        reasoning = rec["reasoning"]
        
        # 4. Assert isolation
        assert "Validation Override" not in reasoning, f"API leaked validation fixture in production mode! Reasoning: {reasoning}"
        print(f"API Isolation Test Success: Reasoning was '{reasoning}'")
        
    finally:
        await redis_bus.delete(f"fixture:{ticker.upper()}")
        settings.STEP12_VALIDATION_MODE = original_mode
