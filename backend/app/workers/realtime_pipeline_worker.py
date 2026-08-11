"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Coordinates realtime market/news pipeline jobs during application runtime.
"""
import asyncio
import json
import time
from loguru import logger
from app.core.redis_client import redis_bus
from app.services.ai_engine.recommender import recommender_service
from app.services.ai_engine.forecast_model import predict_price
from app.core.db import AsyncSessionLocal
from app.models.all_models import Asset
from sqlalchemy import select

class RealTimePipelineWorker:
    """
    [STEP 10] Real-Time Orchestration Worker.
    Subscribes to market and news events, triggers AI processing, and completes the E2E loop.
    """
    def __init__(self):
        self.asset_map = {} # ticker -> asset_id
        self.last_proc = {} # ticker -> timestamp (Throttling for performance)
        self.is_running = True

    async def load_assets(self):
        """Pre-load asset mapping for fast lookups."""
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(Asset))
                assets = res.scalars().all()
                self.asset_map = {a.ticker: a.id for a in assets}
                logger.info(f"RealTimeWorker: Loaded {len(self.asset_map)} assets for pipeline orchestration.")
        except Exception as e:
            logger.error(f"RealTimeWorker: Asset load failure: {e}")

    async def handle_market_tick(self, payload: dict):
        """On Market Tick: Predict -> Recommend -> Publish."""
        ticker = payload.get("symbol")
        asset_id = self.asset_map.get(ticker)
        if not asset_id:
            return

        # [PERF] Throttle background AI processing to 1Hz per ticker to protect RPS
        now = time.time()
        if ticker in self.last_proc and now - self.last_proc[ticker] < 1.0:
            return
        self.last_proc[ticker] = now

        start_time = time.time()
        backend_in_ts = payload.get("ingest_ts", start_time)
        
        try:
            # 1. Trigger fresh forecast based on the new tick (which is already in DB)
            pred_res = await predict_price(asset_id, ingest_ts=backend_in_ts)
            
            # 2. Generate new recommendation
            p_ts = pred_res.get("process_ts") if pred_res else None
            await recommender_service.generate_recommendation(
                asset_id, 
                trigger_source="market_tick",
                ingest_ts=backend_in_ts,
                process_ts=p_ts
            )
            
            end_time = time.time()
            delay_ms = (end_time - backend_in_ts) * 1000
            
            logger.info(f"[E2E][MARKET_IN] {ticker} | Backend Process Time: {delay_ms:.2f}ms")
        except Exception as e:
            logger.error(f"RealTimeWorker: Market Tick Pipeline Error [{ticker}]: {e}")

    async def handle_news_scored(self, payload: dict):
        """On News Event: Predict -> Recommend -> Publish for each affected ticker."""
        tickers = payload.get("tickers", [])
        start_time = time.time()
        backend_in_ts = payload.get("ingest_ts", start_time)

        if not tickers:
            logger.info(f"[E2E][NEWS_IN] Generic News (No Tickers) | Headline: {payload.get('headline')[:30]}...")
            return

        try:
            tasks = []
            for ticker in tickers:
                asset_id = self.asset_map.get(ticker)
                if asset_id:
                    # Define a small helper to run both steps per ticker
                    async def process_ticker(aid, its):
                        pred_res = await predict_price(aid, ingest_ts=its)
                        p_ts = pred_res.get("process_ts") if pred_res else None
                        await recommender_service.generate_recommendation(
                            aid, 
                            trigger_source="news_scored",
                            ingest_ts=its,
                            process_ts=p_ts
                        )
                    
                    tasks.append(process_ticker(asset_id, backend_in_ts))
            
            if tasks:
                await asyncio.gather(*tasks)
            
            end_time = time.time()
            delay_ms = (end_time - backend_in_ts) * 1000
            logger.info(f"[E2E][NEWS_IN] {tickers} | Backend Process Time: {delay_ms:.2f}ms | Headline: {payload.get('headline')[:30]}...")
        except Exception as e:
            logger.error(f"RealTimeWorker: News Pipeline Error: {e}")

    async def run(self):
        """Main listening loop."""
        await self.load_assets()
        logger.info("🚀 Real-Time Pipeline Worker Online (Step 10).")
        
        # We need two separate listeners to avoid blocking
        asyncio.create_task(self.listen_market())
        asyncio.create_task(self.listen_news())
        
        while self.is_running:
            await asyncio.sleep(1)

    async def listen_market(self):
        async for message in redis_bus.subscribe("market_ticks"):
            try:
                payload = json.loads(message) if isinstance(message, str) else message
                await self.handle_market_tick(payload)
            except Exception as e:
                logger.error(f"Market Listener Error: {e}")

    async def listen_news(self):
        async for message in redis_bus.subscribe("news_scored"):
            try:
                payload = json.loads(message) if isinstance(message, str) else message
                await self.handle_news_scored(payload)
            except Exception as e:
                logger.error(f"News Listener Error: {e}")

# Singleton
realtime_pipeline_worker = RealTimePipelineWorker()

if __name__ == "__main__":
    asyncio.run(realtime_pipeline_worker.run())
