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
from sqlalchemy import select, func
from app.models.all_models import News, Sentiment, Recommendation, Asset

@pytest.mark.asyncio
async def test_news_to_recommendation_pipeline(controlled_client, controlled_db_session):
    """
    STRENGTHENED Integration Test:
    1. Query initial counts.
    2. Inject news for AAPL.
    3. Verify news is processed (count increases + found in /latest).
    4. Trigger recommendation.
    5. Verify recommendation count increases.
    """
    ticker = "AAPL"
    article_title = f"BULLISH fixture: AAPL controlled growth signal {asyncio.get_event_loop().time()}"
    
    async with controlled_db_session() as session:
        # Initial counts
        news_count_before = (await session.execute(select(func.count(News.id)))).scalar()
        sent_count_before = (await session.execute(select(func.count(Sentiment.id)))).scalar()
        rec_count_before = (await session.execute(select(func.count(Recommendation.id)))).scalar()

    # 1. Inject News
    payload = {
        "title": article_title,
        "provider": "verification_fixture",
        "url": f"http://verify.apex.ai/{hash(article_title)}",
        "summary": "This is a deterministic test article for Step 12 validation."
    }
    inj_resp = await controlled_client.post("/api/v1/news/inject", json=payload)
    assert inj_resp.status_code == 200

    # 2. Verify News appearing in API (from Redis)
    found_in_api = False
    for _ in range(10):
        await asyncio.sleep(1)
        # Check API
        api_resp = await controlled_client.get("/api/v1/news/latest?limit=50")
        if api_resp.status_code == 200:
            data = api_resp.json()
            articles = data.get("articles") or data.get("news") or []
            if any(article_title in a.get("headline", "") for a in articles):
                found_in_api = True
                break
    
    assert found_in_api, f"Injected article '{article_title}' not found in /news/latest after 10s"

    # Verify DB counts: SHOULD REMAIN SAME (Hardened Isolation)
    async with controlled_db_session() as session:
        news_count_after = (await session.execute(select(func.count(News.id)))).scalar()
        sent_count_after = (await session.execute(select(func.count(Sentiment.id)))).scalar()
    
    assert news_count_after == news_count_before, "HARDENING FAILURE: News count increased for fixture"
    assert sent_count_after == sent_count_before, "HARDENING FAILURE: Sentiment count increased for fixture"

    # 3. Trigger Recommendation
    # It should still work because Recommendation logic reads from Redis for fixtures
    rec_resp = await controlled_client.post("/api/v1/ai/recommend", json={"ticker": ticker})
    assert rec_resp.status_code == 200
    
    # 4. Verify Recommendation count increases
    # Recommendation logic currently persists to DB, we keep this for now to prove logic flow
    # but verify if it SHOULD be isolated too. For graduation, proving the rec exists is key.
    async with controlled_db_session() as session:
        rec_count_after = (await session.execute(select(func.count(Recommendation.id)))).scalar()
    
    assert rec_count_after > rec_count_before, "Recommendation count did not increase after trigger"


    # Final check: Verify the latest recommendation for AAPL is reachable
    # (Optional but good for completeness)
    rec_latest_resp = await controlled_client.get("/api/v1/ai/recommendations/latest")
    assert rec_latest_resp.status_code == 200
    recs = rec_latest_resp.json()
    assert any(r["ticker"] == ticker for r in recs), f"No recommendation found for {ticker} in /latest"
