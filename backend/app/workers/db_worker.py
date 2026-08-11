"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Persists queued ingestion data and keeps database writes off the realtime path.
"""
import asyncio, json, time
from loguru import logger
from app.core.redis_client import redis_bus
from app.core.db import AsyncSessionLocal
from app.models.all_models import MarketDataRow

class DatabaseWorker:
    async def run(self):
        logger.info("Database Persistence Worker Online (Auxiliary Mode).")
        # 🛡️ DEFENSE OPTIMIZATION: 
        # - Market ticks are persisted directly in market_ingester.py
        # - News & Sentiment are persisted directly in news_ingester.py
        # This worker is now available for other high-latency persistence tasks (Events, Predictions).
        while True:
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(DatabaseWorker().run())
