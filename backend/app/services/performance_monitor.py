"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Records latency, throughput, and cache metrics used by performance audit endpoints.
"""
"""
System Performance Monitoring Service.

Tracks real-time telemetry including request latency (avg, p50, p95), error rates, 
throughput (RPS), and cache performance. Metrics are periodically aggregated 
and pushed to Redis for the live monitoring dashboard.
"""
import time
import asyncio
from typing import Dict, List, Any
from collections import deque
import statistics

class PerformanceMonitor:
    """
    Tracks real-time performance metrics: latency, error rates, and throughput.
    """
    def __init__(self, window_size: int = 1000):
        self.request_latencies = deque(maxlen=window_size)
        self.request_count = 0
        self.error_count = 0
        self.start_time = time.time()
        self._lock = asyncio.Lock()

    def record_request(self, latency_ms: float, is_error: bool = False):
        self.request_count += 1
        if is_error:
            self.error_count += 1
        self.request_latencies.append(latency_ms)

    def get_metrics(self) -> Dict[str, Any]:
        lats = list(self.request_latencies)
        p95 = statistics.quantiles(lats, n=20)[18] if len(lats) >= 20 else (max(lats) if lats else 0)
        p50 = statistics.median(lats) if lats else 0
        avg = sum(lats) / len(lats) if lats else 0
        
        uptime = time.time() - self.start_time
        rps = self.request_count / uptime if uptime > 0 else 0
        error_rate = (self.error_count / self.request_count) if self.request_count > 0 else 0
        
        return {
            "avg_latency_ms": round(avg, 2),
            "p50_latency_ms": round(p50, 2),
            "p95_latency_ms": round(p95, 2),
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": round(error_rate, 4),
            "requests_per_second": round(rps, 2),
            "uptime_seconds": round(uptime, 2)
        }

# Global Singleton
monitor = PerformanceMonitor()

def record_metric(latency_ms: float, is_error: bool = False):
    monitor.record_request(latency_ms, is_error)

import json
async def _store_metrics_loop():
    from app.core.redis_client import redis_bus
    from app.services.cache_service import performance_cache
    while True:
        try:
            await asyncio.sleep(10)
            perf = monitor.get_metrics()
            cache = performance_cache.get_stats()
            
            # Flattened format explicitly required
            payload = {
                "avg_latency_ms": perf["avg_latency_ms"],
                "p50_latency_ms": perf["p50_latency_ms"],
                "p95_latency_ms": perf["p95_latency_ms"],
                "request_count": perf["request_count"],
                "error_count": perf["error_count"],
                "error_rate": perf["error_rate"],
                "cache_hits": cache["hits"],
                "cache_misses": cache["misses"],
                "cache_hit_ratio": cache["hit_ratio"],
                "timestamp": time.time()
            }
            await redis_bus.set("system_metrics_live", json.dumps(payload), ex=3600)
        except Exception as e:
            pass

def start_metrics_background_task():
    asyncio.create_task(_store_metrics_loop())
