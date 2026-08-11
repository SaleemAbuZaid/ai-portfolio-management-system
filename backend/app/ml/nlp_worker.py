"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Machine-learning NLP worker helper used by older sentiment processing paths.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Positive and Negative finance vocabulary for deterministic scoring
POS_WORDS = {"surge", "jump", "record", "growth", "approve", "buy", "bullish", "profit", "gain"}
NEG_WORDS = {"plunge", "drop", "hike", "warn", "crash", "bearish", "loss", "sell", "regulate", "ban"}

async def internal_finbert_predict(headline: str) -> float:
    """
    Pseudo-NLP inference. Uses deterministic vocabulary weighting
    to simulate FinBERT compound scoring without loading heavy PyTorch models.
    """
    await asyncio.sleep(0.01) # simulate inference tick
    
    words = set(headline.lower().replace(".", "").replace(",", "").split())
    
    pos_score = len(words.intersection(POS_WORDS))
    neg_score = len(words.intersection(NEG_WORDS))
    
    # Calculate a compound bounded score [-1.0, 1.0]
    total = pos_score + neg_score
    if total == 0:
        return 0.1 # Slight long bias default
        
    compound = (pos_score - neg_score) / total
    return float(compound)

async def nlp_worker_loop(redis_client):
    """
    Subscribes to stream:news_events, categorizes via NLP, and pushes to sentiment stream.
    """
    last_id = "0-0"
    while True:
        try:
            # XREAD block for micro-batch
            messages = await redis_client.xread({"stream:news_events": last_id}, count=5, block=1000)
            if not messages:
                continue
                
            for stream, entries in messages:
                for message_id, msg in entries:
                    payload = json.loads(msg[b"payload"].decode('utf-8'))
                    headline = payload["headline"]
                    
                    # Offload ML to prevent thread locking
                    score = await internal_finbert_predict(headline)
                    
                    sentiment_event = {
                        "article_id": payload["article_id"],
                        "score": score,
                        "nlp_ts": int(datetime.now(timezone.utc).timestamp() * 1000)
                    }
                    
                    await redis_client.xadd("stream:sentiment_events", {"payload": json.dumps(sentiment_event)}, maxlen=1000)
                    last_id = message_id
                    
        except Exception as e:
            logger.error(f"NLP Worker Crash: {e}")
            await asyncio.sleep(1)
