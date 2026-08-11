"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Contains lower-level signal utilities used by model and recommendation experiments.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class ConfluenceMatrix:
    def __init__(self, redis_client):
        self.redis = redis_client
        
    async def evaluate_tick(self, tick_data: dict):
        """
        The Oracle evaluates the tick against recently cached sentiment limits.
        """
        # 1. Fetch Fast-Cache Sentiment
        try:
            raw_sent = await self.redis.get("cache:latest_sentiment_score")
            sentiment_score = float(raw_sent) if raw_sent else 0.0
        except Exception:
            sentiment_score = 0.0
            
        # 2. XGboost Price forecast (Pseudo-Deterministic Momentum)
        # In a full deployment, this queries inference endpoints.
        # We estimate short-term momentum using rolling price history.
        current_price = tick_data["price"]
        
        if not hasattr(self, 'price_history'):
            self.price_history = []
            
        self.price_history.append(current_price)
        if len(self.price_history) > 20: 
            self.price_history.pop(0)
            
        if len(self.price_history) < 5:
            forecast_direction = 0.0
        else:
            # Deterministic momentum: compare current to avg of past
            avg_price = sum(self.price_history) / len(self.price_history)
            diff_pct = (current_price - avg_price) / avg_price
            
            # Bound forecast [-1.0, 1.0]
            # e.g., if we surged 0.1%, it predicts +0.8
            forecast_direction = max(min(diff_pct * 1000.0, 1.0), -1.0)
        
        # 3. Combine Policies
        decision = "WATCH"
        if forecast_direction > 0.6 and sentiment_score > 0.0:
            decision = "BUY"
        elif forecast_direction < -0.4 and sentiment_score < 0.0:
            decision = "SELL"
            
        if decision != "WATCH":
            signal = {
                "signal_id": f"sig_{int(datetime.now(timezone.utc).timestamp())}_{tick_data['asset_id']}",
                "asset_id": tick_data["asset_id"],
                "decision": decision,
                "confidence": abs(forecast_direction),
                "signal_ts": int(datetime.now(timezone.utc).timestamp() * 1000)
            }
            await self.redis.xadd("stream:signal_events", {"payload": json.dumps(signal)}, maxlen=100)
            logger.info(f"Generated {decision} Signal for {tick_data['asset_id']}")
