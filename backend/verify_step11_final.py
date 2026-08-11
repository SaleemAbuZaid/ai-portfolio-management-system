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
import asyncio
import httpx
import time
import json
import os
import logging
from datetime import datetime, timezone
import aiosqlite

# 🛡️ Force absolute path alignment
try:
    from app.core.config import get_settings
    settings = get_settings()
    DB_URL = settings.DATABASE_URL
    # Extract path from sqlite+aiosqlite:///...
    DB_PATH = DB_URL.replace("sqlite+aiosqlite:///", "")
except ImportError:
    # Fallback for standalone run if PYTHONPATH is weird
    DB_PATH = "c:/Users/Gov/Desktop/Medipol/5.1/ENGINEERING PROJECT I/Final/ai_portfolio_gp/backend/apex_defense.db"

BASE_URL = "http://127.0.0.1:8000"
TICKERS = ["BTCUSDT", "ETHUSDT", "AAPL"]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Step11-Final-Audit")

async def check_indexes():
    """Verify that mandatory indexes exist in the LIVE database (SQLite or Postgres)."""
    required_indexes = [
        "idx_price_history_timestamp",
        "idx_price_history_asset_ts",
        "idx_news_published_at",
        "idx_sentiment_news_id",
        "idx_recommendation_timestamp"
    ]
    
    found_indexes = []
    try:
        from app.core.config import get_settings
        settings = get_settings()
        db_url = settings.DATABASE_URL
        
        if "postgresql" in db_url:
            from app.core.db import AsyncSessionLocal
            from sqlalchemy import text
            async with AsyncSessionLocal() as session:
                res = await session.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"))
                found_indexes = [row[0] for row in res.all()]
        else:
            # Fallback to SQLite
            import aiosqlite
            path = db_url.replace("sqlite+aiosqlite:///", "")
            async with aiosqlite.connect(path) as db:
                async with db.execute("SELECT name FROM sqlite_master WHERE type='index'") as cursor:
                    rows = await cursor.fetchall()
                    found_indexes = [row[0] for row in rows]
                
        all_passed = True
        for idx in required_indexes:
            if idx in found_indexes:
                logger.info(f"✅ Index found: {idx}")
            else:
                logger.error(f"❌ Index MISSING: {idx}")
                all_passed = False
                
        return all_passed, found_indexes
    except Exception as e:
        logger.error(f"Failed to check indexes: {e}")
        return False, []

async def warmup_cache():
    """Force cache population by hitting endpoints."""
    logger.info("Warming up Cache (Market & News)...")
    async with httpx.AsyncClient() as client:
        # Market Warmup
        for ticker in TICKERS:
            try:
                await client.get(f"{BASE_URL}/api/v1/market/{ticker}", timeout=30.0)
            except Exception as e:
                logger.warning(f"Market warmup failed for {ticker}: {e}")
        # News Warmup
        try:
            await client.get(f"{BASE_URL}/api/v1/news/latest", timeout=30.0)
        except Exception as e:
            logger.warning(f"News warmup failed: {e}")

async def run_concurrent_load(endpoint, name, duration_secs=5, concurrency=5):
    """Run a concurrent load test."""
    logger.info(f"Running {name} load test ({duration_secs}s, concurrency={concurrency})...")
    
    latencies = []
    total_reqs = 0
    start_time = time.time()
    
    async def worker():
        nonlocal total_reqs
        async with httpx.AsyncClient() as client:
            while time.time() - start_time < duration_secs:
                t_start = time.perf_counter()
                try:
                    resp = await client.get(f"{BASE_URL}{endpoint}", timeout=10.0)
                    if resp.status_code == 200:
                        latencies.append((time.perf_counter() - t_start) * 1000)
                        total_reqs += 1
                except Exception:
                    pass

    await asyncio.gather(*[worker() for _ in range(concurrency)])
    
    total_duration = time.time() - start_time
    rps = total_reqs / total_duration if total_duration > 0 else 0
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    
    return {
        "total_requests": total_reqs,
        "duration": total_duration,
        "rps": rps,
        "avg_latency": avg_lat
    }

async def get_system_telemetry():
    """Fetch telemetry from the production metrics endpoint."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{BASE_URL}/api/v1/metrics/performance", timeout=5.0)
            return resp.json()
        except Exception:
            return None

async def main():
    logger.info("=== STEP 11 FINAL STRICT VERIFICATION ===")
    logger.info(f"Verified DB Path: {DB_PATH}")
    
    # 1. Audit DB
    if "sqlite" in DB_PATH and not os.path.exists(DB_PATH):
        logger.error(f"FATAL: Database file not found at {DB_PATH}")
        return

    index_pass, found_indices = await check_indexes()
    
    # 2. Warmup
    await warmup_cache()
    await asyncio.sleep(2)
    
    # 2.5 Reset metrics for clean audit
    logger.info("Resetting metrics for clean audit run...")
    async with httpx.AsyncClient() as client:
        await client.get(f"{BASE_URL}/api/v1/metrics/performance?reset=true", timeout=5.0)
    
    # 3. Load Tests
    market_results = await run_concurrent_load("/api/v1/market/BTCUSDT", "Market-HotPath", duration_secs=5, concurrency=4)
    news_results = await run_concurrent_load("/api/v1/news/latest", "News-HotPath", duration_secs=5, concurrency=2)
    
    # 4. Telemetry
    telemetry = await get_system_telemetry()
    cache_mode = telemetry.get("cache", {}).get("mode", "Unknown") if telemetry else "Unknown"
    hit_ratio = telemetry.get("cache", {}).get("hit_ratio", 0) if telemetry else 0
    
    # 5. Summary Report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "db_path": DB_PATH,
        "sql_optimization": {"pass": index_pass, "indexes": found_indices},
        "market_perf": market_results,
        "news_perf": news_results,
        "telemetry": telemetry,
        "verdict": "PASS" if index_pass and hit_ratio > 0.7 else "FAIL"
    }
    
    os.makedirs("proof_step12", exist_ok=True)
    with open("proof_step12/step11_v2_results.json", "w") as f:
        json.dump(report, f, indent=4)
        
    with open("proof_step12/STEP11_PASS.txt", "w") as f:
        f.write(f"STEP 11 FINAL VERDICT: {report['verdict']}\n")
        f.write(f"DB Path: {DB_PATH}\n")
        f.write(f"SQL Indexes: {'VERIFIED' if index_pass else 'MISSING'}\n")
        f.write(f"Cache Mode: {cache_mode}\n")
        f.write(f"Cache Hit Ratio: {hit_ratio:.2%}\n")
        f.write(f"Market RPS: {market_results['rps']:.2f} (Avg Lat: {market_results['avg_latency']:.2f}ms)\n")
        f.write(f"News RPS: {news_results['rps']:.2f} (Avg Lat: {news_results['avg_latency']:.2f}ms)\n")

    # Update split proof files for backward compatibility
    with open("proof_step12/step11_load_test.txt", "w") as f:
        f.write(f"Market RPS: {market_results['rps']:.2f}\n")
        f.write(f"News RPS: {news_results['rps']:.2f}\n")
        f.write(f"Market Latency: {market_results['avg_latency']:.2f}ms\n")
        
    with open("proof_step12/step11_cache_metrics.txt", "w") as f:
        f.write(f"Mode: {cache_mode}\n")
        f.write(f"Hit Ratio: {hit_ratio:.2%}\n")
        
    with open("proof_step12/step11_query_optimization.txt", "w") as f:
        f.write(f"DB: {DB_PATH}\n")
        f.write(f"Indexes: {', '.join(found_indices)}\n")

    print("\n" + "="*50)
    print("FINAL STEP 11 PERFORMANCE AUDIT RESULTS")
    print("="*50)
    print(f"Database: {DB_PATH}")
    print(f"SQL Indexes: {'PASS' if index_pass else 'FAIL'}")
    print(f"Cache Mode: {cache_mode}")
    print(f"Cache Hit Ratio: {hit_ratio*100:.2f}%")
    print(f"Market Hot-Path: {market_results['rps']:.2f} RPS | {market_results['avg_latency']:.2f}ms")
    print(f"News Hot-Path:   {news_results['rps']:.2f} RPS | {news_results['avg_latency']:.2f}ms")
    print("-" * 50)
    print(f"FINAL VERDICT: {report['verdict']}")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
