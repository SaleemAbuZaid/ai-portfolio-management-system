"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Initializes the FastAPI application, routers, middleware, and background ingestion topology.
- Serves as the runtime entry point for market data, news, AI advice, and dashboard APIs.
"""
import asyncio, os, time, json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

# Core configuration and infrastructure are imported before routers so startup
# can initialize Redis and the database from one place.
from app.core.config import get_settings
from app.core.redis_client import redis_bus
from app.core.db import init_models


t0 = time.time()
from app.api.v1.portfolio import router as portfolio_router


t0 = time.time()
from app.api.v1.market import router as market_router


t0 = time.time()
from app.api.v1.news import router as news_router


t0 = time.time()
from app.api.v1.ai import router as ai_router


t0 = time.time()
from app.api.v1.metrics import router as metrics_router


t0 = time.time()
from app.api.v1.health import router as health_router

from app.api.v1.admin import router as admin_router
from app.api.v1.broker import router as broker_router
from app.api.v1.auth import router as auth_router
from app.api.v1.user import router as user_router


t0 = time.time()
from app.api.websockets.stream import stream_manager


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start and stop the backend runtime topology around the FastAPI application.

    Startup connects Redis, initializes/migrates/seeds the database once, and
    schedules ingestion, NLP, quant, recommender, and execution workers.
    """
    from app.services.ingestion.market_ingester import market_ingester
    from app.services.ingestion.news_ingester import news_ingester
    from app.workers.db_worker import DatabaseWorker
    from app.workers.nlp_worker import nlp_worker
    from app.workers.quant_worker import quant_worker
    from app.workers.execution_worker import ExecutionWorker
    from app.workers.realtime_pipeline_worker import realtime_pipeline_worker
    from app.core.seed import seed_database
    
    # Infrastructure boot: connect shared services before scheduling workers.
    logger.info("🚀 Booting Apex AI Ingest & Persistence Topology...")
    await redis_bus.connect()
    
    # A Redis lock ensures only one Uvicorn worker initializes/migrates/seeds
    # the database, avoiding duplicate startup writes in multi-worker runs.
    lock_key = "apex:init_lock"
    is_master = await redis_bus.set(lock_key, "locked", ex=120, nx=True)
    
    if is_master:
        logger.info("🛠️ [INIT] Master worker starting DB initialization...")
        await init_models()
        from app.core.migrations import run_migrations
        await run_migrations()
        await seed_database()
        logger.info("✅ [INIT] DB initialization complete.")
    else:
        logger.info("💤 [INIT] Secondary worker skipping DB initialization.")
        # Give the master worker time to create tables before local tasks start.
        await asyncio.sleep(10) 
    
    # Launch service topology after database initialization is settled.
    db_worker = DatabaseWorker()
    execution_worker = ExecutionWorker()
    
    async def periodic_recommender():
        """
        Generate periodic AI recommendations for every known asset.

        The loop runs in the master worker and persists recommendations so the
        dashboard can show database-backed advice even without manual triggers.
        """
        from app.services.ai_engine.recommender import recommender_service
        from app.services.ai_engine.forecast_model import predict_price
        from app.models.all_models import Asset
        from sqlalchemy import select
        
        while True:
            try:
                from app.core.db import AsyncSessionLocal
                async with AsyncSessionLocal() as session:
                    res = await session.execute(select(Asset.id))
                    asset_ids = res.scalars().all()
                    
                for aid in asset_ids:
                    # Keep the background loop cooperative during model work.
                    await predict_price(aid)
                    await recommender_service.generate_recommendation(aid)
                    await asyncio.sleep(0.1)
                    
                logger.info(f"🔮 [BACKGROUND] Recommender cycle complete for {len(asset_ids)} assets.")
            except Exception as e:
                logger.error(f"Background Recommender Error: {e}")
            
            await asyncio.sleep(45)

    async def periodic_performance_logger():
        """Logs performance metrics every 10s for observability and stores them in Redis."""
        from app.services.performance_monitor import monitor
        from app.services.cache_service import performance_cache
        import json
        while True:
            await asyncio.sleep(10) # 10s interval for active monitoring
            perf = monitor.get_metrics()
            cache = performance_cache.get_stats()
            logger.info(f"📊 [PERF] RPS: {perf['requests_per_second']} | p95: {perf['p95_latency_ms']}ms | Cache Ratio: {cache['hit_ratio']:.2%}")
            
            try:
                payload = {
                    "avg_latency_ms": perf["avg_latency_ms"],
                    "p50_latency_ms": perf.get("p50_latency_ms", 0),
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
                logger.error(f"Failed to store performance metrics to Redis: {e}")

    tasks = []
    try:
        # Local tasks run on every worker so each process can serve WebSockets.
        tasks.extend([
            asyncio.create_task(stream_manager.broadcast_from_redis("market_ticks")),
            asyncio.create_task(stream_manager.broadcast_from_redis("ai_signals")),
            asyncio.create_task(stream_manager.broadcast_from_redis("news_scored")),
            asyncio.create_task(stream_manager.broadcast_from_redis("trade_executed")),
            asyncio.create_task(stream_manager.broadcast_from_redis("recommendations")),
            asyncio.create_task(stream_manager.run_heartbeat())
        ])
        
        # Global ingestion/inference tasks run only on the master worker.
        if is_master:
            logger.success("🏆 [MASTER] Scheduling Global Ingestion & Inference Loops.")
            tasks.extend([
                asyncio.create_task(market_ingester.run()),
                asyncio.create_task(news_ingester.run()),
                asyncio.create_task(realtime_pipeline_worker.run()),
                asyncio.create_task(db_worker.run()),
                asyncio.create_task(execution_worker.run()),
                asyncio.create_task(periodic_recommender()),
                asyncio.create_task(periodic_performance_logger())
            ])
        else:
            logger.info("👥 [WORKER] Background tasks restricted to local broadcasting.")

        logger.success("💎 Apex AI System tasks scheduled.")
    except Exception as e:
        logger.error(f"Failed to schedule background tasks: {e}")
    
    logger.success("💎 Apex AI System fully operational (Defense Mode).")
    yield
    
    # Shutdown cancels background tasks and closes the shared Redis client.
    for task in tasks: task.cancel()
    await redis_bus.close()

app = FastAPI(
    title="APEX AI Portfolio Management API",
    version=settings.VERSION,
    lifespan=lifespan,
    debug=settings.DEBUG,
)



app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3001",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.services.performance_monitor import record_metric

class PerformanceMiddleware(BaseHTTPMiddleware):
    """
    Records request latency and error status for every FastAPI request.

    The performance monitor uses this middleware to populate dashboard and audit
    metrics without changing the response returned by each API route.
    """
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        is_error = False
        try:
            response = await call_next(request)
            if response.status_code >= 400:
                is_error = True
            return response
        except Exception:
            is_error = True
            raise
        finally:
            latency_ms = (time.perf_counter() - start_time) * 1000
            record_metric(latency_ms, is_error)

app.add_middleware(PerformanceMiddleware)

@app.get("/health")
async def health_check():
    """Return a small liveness payload for load balancers and smoke tests."""
    return {
        "status": "ok", 
        "timestamp": time.time(),
        "mode": settings.TRADING_MODE
    }

# Source-health endpoints moved to market.py router for better consistency and to avoid catch-all conflicts.

# Register fixed API routers before catch-all static frontend routes.
app.include_router(portfolio_router, prefix="/api/v1/portfolio", tags=["Portfolio"])
app.include_router(market_router, prefix="/api/v1/market", tags=["Market"])
app.include_router(news_router, prefix="/api/v1/news", tags=["News"])
app.include_router(ai_router, prefix="/api/v1/ai", tags=["AI"])
app.include_router(metrics_router, prefix="/api/v1/metrics", tags=["Metrics"])
app.include_router(health_router, prefix="/api/v1/health", tags=["Health"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(broker_router, prefix="/api/v1/broker", tags=["Broker"])
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(user_router, prefix="/api/v1/user", tags=["User"])

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint that relays Redis-backed market/news/AI events."""
    await stream_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        stream_manager.disconnect(websocket)

# Global fault tolerance keeps unhandled exceptions in a consistent JSON shape.
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception(f"🔴 [GLOBAL_ERROR] {exc}")
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )



@app.get("/status")
async def get_status():
    """Top-level health and truth-label tracking."""
    from app.services.ingestion.market_ingester import market_ingester
    return {s: i.get("status", i.get("label", "UNKNOWN")) for s, i in market_ingester.source_status.items()}

# Avatar uploads are mounted independently from the React build so profile
# images work even when the frontend bundle is served elsewhere.
os.makedirs("static/uploads/avatars", exist_ok=True)
app.mount("/static/uploads", StaticFiles(directory="static/uploads"), name="uploads")

# Alias retained for dashboard/admin clients that call /providers/health.
@app.get("/api/v1/providers/health", tags=["Health"])
async def providers_health_alias():
    from app.api.v1.health import health_providers
    return await health_providers()

# Serve the production React build when it exists in the repository.
frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "build")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
    
    # SPA catch-all redirects non-API/non-static paths to index.html.
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("redoc") or full_path.startswith("static/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        return FileResponse(os.path.join(frontend_path, "index.html"))
else:
    logger.error(f"❌ Frontend path not found at {frontend_path}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
