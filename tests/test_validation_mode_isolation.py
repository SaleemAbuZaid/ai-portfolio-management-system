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
from datetime import datetime, timezone
from app.core.config import settings
from app.core.redis_client import redis_bus
from app.services.ai_engine.recommender import recommender_service
from app.core.db import AsyncSessionLocal
from app.models.all_models import Asset, Prediction, Sentiment, PriceHistory
from sqlalchemy import select

@pytest.mark.asyncio
async def test_validation_mode_isolation():
    """
    Assert that if STEP12_VALIDATION_MODE is False, the recommender ignores Redis fixtures.
    This ensures that live production mode is completely isolated from validation logic.
    """
    # 1. Force validation mode to False for this test isolation
    original_mode = settings.STEP12_VALIDATION_MODE
    settings.STEP12_VALIDATION_MODE = False
    
    ticker = "AAPL"
    try:
        async with AsyncSessionLocal() as session:
            # Ensure AAPL exists and has some baseline data for normal logic to work
            asset_res = await session.execute(select(Asset).where(Asset.ticker == ticker))
            asset = asset_res.scalar_one_or_none()
            if not asset:
                asset = Asset(ticker=ticker, name="Apple Inc", asset_class="EQUITY")
                session.add(asset)
                await session.flush()
            
            asset_id = asset.id
            now = datetime.now(timezone.utc)
            
            # Add a baseline price if missing
            price_res = await session.execute(select(PriceHistory).where(PriceHistory.asset_id == asset_id).limit(1))
            if not price_res.scalar_one_or_none():
                session.add(PriceHistory(asset_id=asset_id, price=150.0, timestamp=now))
            
            # Add a baseline prediction if missing
            pred_res = await session.execute(select(Prediction).where(Prediction.asset_id == asset_id).limit(1))
            if not pred_res.scalar_one_or_none():
                session.add(Prediction(asset_id=asset_id, target_price=155.0, timestamp=now))
            
            await session.commit()

        fixture_key = f"fixture:{ticker.upper()}"
        
        # 2. Manually set a fixture in Redis (simulating a leaked or rogue fixture)
        fixture_data = {
            "sentiment": 0.99,
            "forecast": 0.09,
            "ts": time.time()
        }
        await redis_bus.set(fixture_key, json.dumps(fixture_data), ex=30)
        
        # 3. Generate recommendation while in LIVE mode (Validation=False)
        recommendation = await recommender_service.generate_recommendation(asset_id)
        
        # 4. Assertions
        # The reasoning should NOT contain "Validation Override"
        # It should instead contain the normal logic reasoning like "Bullish Score" or "Neutral Score"
        reasoning = recommendation["reasoning"]
        assert "Validation Override" not in reasoning, f"Expected normal reasoning, but found validation override: {reasoning}"
        print(f"Isolation Test Success: Reasoning was '{reasoning}'")
        
    finally:
        # Cleanup fixture and restore mode
        await redis_bus.delete(f"fixture:{ticker.upper()}")
        settings.STEP12_VALIDATION_MODE = original_mode
