"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Creates database indexes used by performance-sensitive audit and dashboard queries.
"""
import asyncio
from sqlalchemy import text
from app.core.db import engine, init_models
from loguru import logger

async def apply_performance_indexes():
    """
    STRICT REPAIR: Explicitly create indexes for hot-path performance.
    Base.metadata.create_all does NOT add indexes to existing tables.
    """
    indexes = [
        # Price History: asset_id + timestamp is common for latest price
        ("idx_price_history_timestamp", "price_history", "timestamp"),
        ("idx_price_history_asset_ts", "price_history", "asset_id, timestamp"),
        
        # News: published_at for latest news fetches
        ("idx_news_published_at", "news", "published_at"),
        
        # Sentiment: news_id and asset_id for filtering
        ("idx_sentiment_news_id", "sentiment", "news_id"),
        ("idx_sentiment_asset_id", "sentiment", "asset_id"),
        
        # Recommendations: timestamp for signal streams
        ("idx_recommendation_timestamp", "recommendations", "timestamp")
    ]
    
    async with engine.begin() as conn:
        logger.info("Applying Step 11 Performance Indexes...")
        for idx_name, table, columns in indexes:
            try:
                # SQLite syntax
                await conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({columns});"))
                logger.info(f"Verified index: {idx_name} on {table}({columns})")
            except Exception as e:
                logger.error(f"Failed to create index {idx_name}: {e}")

if __name__ == "__main__":
    asyncio.run(apply_performance_indexes())
