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
import asyncio
import time

@pytest.mark.asyncio
async def test_market_cache_behavior(controlled_client):
    """
    STRICT Step 11/12 Verification:
    Verify that /api/v1/market/{ticker} returns source='cache' on second call.
    """
    ticker = "AAPL"
    
    # 🕒 Robustness: Wait for seeding to complete (up to 30s)
    db_assets = []
    has_prices = False
    for i in range(30):
        resp = await controlled_client.get(f"/api/v1/market/{ticker}")
        if resp.status_code == 200:
            break
        
        # Diagnostic: Check what's actually in the DB
        try:
            from app.core.db import AsyncSessionLocal
            from app.models.all_models import Asset, PriceHistory
            from sqlalchemy import select, func
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(Asset.ticker))
                db_assets = [r[0] for r in res.all()]
                
                aapl_res = await session.execute(select(Asset.id).where(Asset.ticker == "AAPL"))
                aapl_id = aapl_res.scalar_one_or_none()
                if aapl_id:
                    p_res = await session.execute(select(func.count(PriceHistory.id)).where(PriceHistory.asset_id == aapl_id))
                    has_prices = p_res.scalar() > 0
        except Exception as e:
            print(f"DB Check Failed: {e}")
            
        print(f"DEBUG [Attempt {i}]: DB Assets: {db_assets} | AAPL Has Prices: {has_prices}")
        if resp.status_code == 404:
            try:
                print(f"DEBUG [Attempt {i}]: 404 Body: {resp.json()}")
            except:
                print(f"DEBUG [Attempt {i}]: 404 Text: {resp.text}")
        
        await asyncio.sleep(1)
    
    assert resp.status_code == 200, f"Asset {ticker} not seeded in time. DB Assets: {db_assets}, Has Prices: {has_prices}. Body: {resp.text}"
    
    # First call: Warm the cache
    resp1 = await controlled_client.get(f"/api/v1/market/{ticker}")
    assert resp1.status_code == 200
    
    # Wait for async cache set
    await asyncio.sleep(1.0)
    
    # Second call: Should hit cache
    resp2 = await controlled_client.get(f"/api/v1/market/{ticker}")
    assert resp2.status_code == 200
    data2 = resp2.json()
    
    # Verify Step 11 performance requirement
    assert data2.get("source") == "cache", f"Expected source='cache' for {ticker}, got '{data2.get('source')}'"
    print(f"✅ Cache verified for {ticker}")

@pytest.mark.asyncio
async def test_news_cache_behavior(controlled_client):
    """
    STRICT Step 11/12 Verification:
    Verify that /api/v1/news/latest returns source='cache' on second call.
    """
    # 🕒 Robustness: Ensure at least one news item exists (it should be seeded, but let's be sure)
    # If not seeded, we inject one.
    resp_init = await controlled_client.get("/api/v1/news/latest")
    if resp_init.status_code != 200 or not (resp_init.json().get("articles") or resp_init.json().get("news")):
        await controlled_client.post("/api/v1/news/inject", json={
            "title": "Verification Event: Market Volatility Low",
            "provider": "verification_system"
        })
        await asyncio.sleep(1.0) # Wait for processing

    # First call
    resp1 = await controlled_client.get("/api/v1/news/latest")
    assert resp1.status_code == 200
    
    await asyncio.sleep(1.0)
    
    # Second call
    resp2 = await controlled_client.get("/api/v1/news/latest")
    assert resp2.status_code == 200
    data2 = resp2.json()
    
    # The source is usually in a top-level field for aggregated routes
    assert data2.get("source") == "cache", f"Expected source='cache' for news, got '{data2.get('source')}'"
    print("✅ Cache verified for News API")
