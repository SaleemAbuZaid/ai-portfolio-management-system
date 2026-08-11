"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Legacy news worker entry point kept for ingestion compatibility checks.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
import aiohttp

logger = logging.getLogger(__name__)

async def news_ingestor(redis_client, stream_name: str = "stream:news_events"):
    """
    Async loop fetching real news from CryptoCompare via Free API.
    Pushes valid crypto headlines to Redis awaiting NLP tagging.
    """
    last_fetched_id = None
    url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        articles = data.get("Data", [])
                        
                        # Process only new articles (up to 5 per poll to prevent flood)
                        new_articles = [a for a in articles if last_fetched_id is None or a["id"] > last_fetched_id][:5]
                        
                        if new_articles:
                            last_fetched_id = max(a["id"] for a in new_articles)
                            
                        for article in reversed(new_articles):
                            doc = {
                                "article_id": f"cryptocompare_{article['id']}",
                                "provider": article.get("source", "cryptocompare"),
                                "ingest_ts": int(datetime.now(timezone.utc).timestamp() * 1000),
                                "headline": article.get("title", ""),
                                "symbols": article.get("categories", "").split("|")
                            }
                            await redis_client.xadd(stream_name, {"payload": json.dumps(doc)}, maxlen=1000)
                            logger.info(f"Ingested real news event: {doc['headline'][:40]}...")
                            
            # Don't violate rate limits
            await asyncio.sleep(15) 
        except Exception as e:
            logger.error(f"News ingestion error: {e}")
            await asyncio.sleep(5)
