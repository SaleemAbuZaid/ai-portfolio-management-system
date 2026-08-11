"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Provides cache helpers used for low-latency market, news, and performance reads.
"""
import time
import json
import logging
from typing import Any, Optional, Dict
from app.core.redis_client import redis_bus

logger = logging.getLogger("PerformanceCache")

class PerformanceCache:
    """
    Centralized caching layer for Step 11.
    Handles TTL, hit/miss tracking, and automatic fallback.
    """
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.latencies = [] # List of recent read latencies in ms
        self.start_time = time.time()

    async def get(self, key: str) -> Optional[Any]:
        t0 = time.perf_counter()
        try:
            raw = await redis_bus.get(key)
            latency = (time.perf_counter() - t0) * 1000
            self.latencies.append(latency)
            if len(self.latencies) > 1000:
                self.latencies.pop(0)

            if raw:
                self.hits += 1
                logger.debug(f"Cache HIT: {key}")
                try:
                    return json.loads(raw)
                except:
                    return raw
            else:
                self.misses += 1
                logger.debug(f"Cache MISS: {key}")
                return None
        except Exception as e:
            logger.error(f"Cache GET Error for {key}: {e}")
            self.misses += 1
            return None

    async def set(self, key: str, value: Any, ttl: int = 60):
        """Sets a value with TTL (seconds)."""
        try:
            payload = json.dumps(value) if not isinstance(value, str) else value
            await redis_bus.set(key, payload, ex=ttl)
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
        except Exception as e:
            logger.error(f"Cache SET Error for {key}: {e}")

    def get_stats(self) -> Dict[str, Any]:
        from app.core.redis_client import redis_bus
        total = self.hits + self.misses
        ratio = (self.hits / total) if total > 0 else 0
        avg_latency = (sum(self.latencies) / len(self.latencies)) if self.latencies else 0
        
        # Determine mode
        is_redis = redis_bus.client is not None
        from app.core.config import get_settings
        is_strict = get_settings().LIVE_VERIFY_MODE
        
        mode_str = "Redis" if is_redis else "In-Memory Fallback"
        if is_strict:
            mode_str = "STRICT REDIS (LIVE)" if is_redis else "STRICT FAIL (NO REDIS)"

        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": ratio,
            "avg_latency_ms": avg_latency,
            "mode": mode_str,
            "uptime_seconds": time.time() - self.start_time
        }

    def reset_stats(self):
        self.hits = 0
        self.misses = 0
        self.latencies = []

# Singleton
performance_cache = PerformanceCache()
