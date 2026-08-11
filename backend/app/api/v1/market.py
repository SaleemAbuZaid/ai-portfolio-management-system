"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Serves market snapshots, price history, source health, and manual test injection routes.
- Uses cache-first reads and explicit provenance labels so dashboard prices remain auditable.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import logging
import time
import json
from datetime import datetime, timedelta, timezone
from app.services.ingestion.market_ingester import market_ingester
from app.core.redis_client import redis_bus
from app.services.cache_service import performance_cache
from app.services.performance_monitor import record_metric
from app.core.db import AsyncSessionLocal
from app.models.all_models import PriceHistory, Asset
from sqlalchemy import select, desc
from app.core.symbols import normalize_symbol
from app.core.sanitizer import sanitize_provider_name
from app.core.config import settings

TRACKED_ASSETS = [
    "AAPL", "TSLA", "BTC/USD", "ETH/USD", "EUR/USD", "GBP/USD", 
    "USD/TRY", "USD/JPY", "XAU/USD", "XAG/USD", "WTI", "BRENT"
]

LIVE_PROVIDER_FRESHNESS_SECONDS = 300

router = APIRouter()
logger = logging.getLogger(__name__)

class AssetResponse(BaseModel):
    """
    Minimal market response schema for asset status endpoints.

    It keeps ticker, latest price, and status together for lightweight API
    checks without requiring the full dashboard snapshot payload.
    """
    ticker: str
    latest_price: float
    status: str

@router.get("/status/snapshot")
async def get_market_snapshot():
    """
    Return the consolidated market snapshot for all dashboard-tracked assets.

    Each row includes price, trend, freshness, provider, and source_type so the
    frontend can display LIVE, DELAYED, HISTORY_DB, or INTERNAL_FALLBACK honestly.
    """
    snapshot = []
    now_utc = datetime.now(timezone.utc)
    # Asset metadata is loaded once so the snapshot does not open a new session
    # for every ticker just to resolve the display class.
    asset_metadata = {}
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Asset.ticker, Asset.asset_class))
        for row in res.all():
            asset_metadata[row[0]] = row[1]

    try:
        for t in TRACKED_ASSETS:
            asset_data = None
            a_class = asset_metadata.get(t, "EQUITY")
            
            # Prefer the hot Redis/performance cache because it carries the
            # freshest provider timestamp and provenance label from ingestion.
            tick = await performance_cache.get(f"latest:tick:{t}")
            if tick:
                ingest_ts = tick.get("ingest_ts", time.time())
                provider_ts = tick.get("provider_ts") or ingest_ts
                if provider_ts > 10000000000:
                    provider_ts = provider_ts / 1000.0
                # Provider timestamps may arrive as seconds, milliseconds, or
                # naive datetimes; normalize them before classifying freshness.
                tick_ts = datetime.fromtimestamp(provider_ts, tz=timezone.utc)
                freshness = int((now_utc - tick_ts).total_seconds())
                ingest_freshness = int(now_utc.timestamp() - float(ingest_ts))
                
                # A stored basis price is used for trend only; it does not
                # change the provenance label of the latest quote.
                old_price = await _get_historical_basis_price(t)
                current_p = float(tick.get("price", 0.0))
                change_pct = 0.0
                if old_price > 0:
                    change_pct = ((current_p - old_price) / old_price) * 100.0
                
                # If the only available basis is the current quote, expose
                # "insufficient history" by leaving change_pct as null.
                is_stale_basis = (old_price == current_p)
                final_change = round(change_pct, 2) if (old_price > 0 and not is_stale_basis) else None
                
                provider_name = sanitize_provider_name(tick.get("provider"))
                provider_upper = provider_name.upper()
                status_label = tick.get("status_label")
                is_twelvedata = "TWELVEDATA" in provider_upper
                is_alphavantage = "ALPHAVANTAGE" in provider_upper
                is_binance = "BINANCE" in provider_upper
                is_internal = any(x in provider_upper for x in ["INTERNAL", "BACKUP", "INJECTION"])
                
                # Source labels are intentionally conservative. Free APIs may
                # return delayed quotes, stale cache entries, or no data, so the
                # dashboard only shows LIVE_PROVIDER when freshness proves it.
                source_type = "UNKNOWN"
                if status_label == "LIVE_PROVIDER" and freshness <= LIVE_PROVIDER_FRESHNESS_SECONDS:
                    source_type = "LIVE_PROVIDER"
                elif status_label == "DELAYED_PROVIDER":
                    source_type = "DELAYED_PROVIDER"
                elif status_label == "INTERNAL_FALLBACK":
                    source_type = "INTERNAL_FALLBACK"
                elif (is_twelvedata or is_binance) and freshness <= LIVE_PROVIDER_FRESHNESS_SECONDS:
                    source_type = "LIVE_PROVIDER"
                elif (is_twelvedata or is_alphavantage or is_binance):
                    source_type = "DELAYED_PROVIDER"
                elif is_internal:
                    source_type = "INTERNAL_FALLBACK"
                else:
                    source_type = "DELAYED_PROVIDER"

                asset_data = {
                    "ticker": t,
                    "latest_price": current_p,
                    "trend_basis": old_price,
                    "change_pct": final_change,
                    "timestamp": tick_ts.isoformat(),
                    "status": "LIVE" if source_type == "LIVE_PROVIDER" else "DELAYED" if source_type == "DELAYED_PROVIDER" else "FALLBACK",
                    "provider": provider_name,
                    "source_type": source_type,
                    "is_live_provider": (source_type == "LIVE_PROVIDER"),
                    "is_internal_fallback": is_internal,
                    "provider_status": "CONNECTED" if ((is_twelvedata or is_alphavantage or is_binance) and ingest_freshness < 600) else "DISCONNECTED",
                    "lag_ms": max(0.0, float(tick.get("lag_ms", 0.0))),
                    "freshness_seconds": max(0, freshness),
                    "asset_class": a_class
                }

            # If the live cache is cold, use persisted history and label the
            # response as HISTORY/DELAYED-style data instead of live telemetry.
            if not asset_data:
                async with AsyncSessionLocal() as session:
                    res = await session.execute(select(Asset.id).where(Asset.ticker == t))
                    a_id = res.scalar_one_or_none()
                    
                    if a_id:
                        stmt_latest = (
                            select(PriceHistory.price, PriceHistory.timestamp, PriceHistory.provider)
                            .where(PriceHistory.asset_id == a_id)
                            .order_by(desc(PriceHistory.timestamp))
                            .limit(1)
                        )
                        p_res = await session.execute(stmt_latest)
                        latest = p_res.one_or_none()
                        
                        if latest:
                            latest_ts = latest.timestamp
                            if latest_ts.tzinfo is None:
                                latest_ts = latest_ts.replace(tzinfo=timezone.utc)
                                
                            freshness = int((now_utc - latest_ts).total_seconds())
                            old_price = await _get_historical_basis_price(t)
                            change_pct = 0.0
                            if old_price > 0:
                                change_pct = ((latest.price - old_price) / old_price) * 100.0

                            provider_name = sanitize_provider_name(latest.provider or "Historical DB")
                            is_internal = any(x in provider_name.upper() for x in ["INTERNAL", "BACKUP"])

                            # Avoid implying a flat market when the database has
                            # only one usable price point for the asset.
                            is_stale_basis = (old_price == latest.price)
                            
                            asset_data = {
                                "ticker": t,
                                "latest_price": latest.price,
                                "trend_basis": old_price,
                                "change_pct": round(change_pct, 2) if (old_price > 0 and not is_stale_basis) else None,
                                "timestamp": latest_ts.isoformat(),
                                "status": "DELAYED_DB",
                                "provider": provider_name,
                                "source_type": "INTERNAL_FALLBACK" if is_internal else "DELAYED_PROVIDER",
                                "is_live_provider": False,
                                "is_internal_fallback": is_internal,
                                "provider_status": "INTERNAL_ONLY" if is_internal else "DISCONNECTED",
                                "lag_ms": float(freshness) * 1000.0,
                                "freshness_seconds": max(0, freshness),
                                "asset_class": a_class
                            }

            # Final offline row keeps the dashboard shape stable without
            # claiming that a provider produced a usable quote.
            if not asset_data:
                asset_data = {
                    "ticker": t,
                    "latest_price": 0.0,
                    "trend_basis": 0.0,
                    "change_pct": 0.0,
                    "timestamp": now_utc.isoformat(),
                    "status": "OFFLINE",
                    "provider": "missing",
                    "asset_class": a_class
                }
            
            snapshot.append(asset_data)

        # The defense dashboard expects the configured 12-asset universe.
        if len(snapshot) != 12:
            logger.warning(f"Snapshot mismatch: {len(snapshot)} items instead of 12.")

        return snapshot
    except Exception as e:
        logger.error(f"Error in get_market_snapshot: {e}", exc_info=True)
        if snapshot: return snapshot
        return [{"ticker": "ERROR", "status": "ERROR", "provider": str(e), "latest_price": 0.0, "change_pct": 0.0, "source_type": "ERROR"}]

async def _get_historical_basis_price(ticker: str) -> float:
    """
    Return a stored comparison price for trend calculation.

    The function looks for a price near 24 hours ago, then falls back to the
    previous stored row. It exists so the market snapshot can show movement
    without reclassifying the latest provider source.
    """
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Asset.id).where(Asset.ticker == ticker))
            a_id = res.scalar_one_or_none()
            if not a_id: return 0.0
            
            # Look for a price from ~24h ago
            one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
            stmt = (
                select(PriceHistory.price)
                .where(PriceHistory.asset_id == a_id)
                .where(PriceHistory.timestamp <= one_day_ago)
                .order_by(desc(PriceHistory.timestamp))
                .limit(1)
            )
            p_res = await session.execute(stmt)
            old_price = p_res.scalar_one_or_none()
            if old_price: return float(old_price)
            
            # Fallback to the second-to-last price
            stmt = (
                select(PriceHistory.price)
                .where(PriceHistory.asset_id == a_id)
                .order_by(desc(PriceHistory.timestamp))
                .offset(1)
                .limit(1)
            )
            p_res = await session.execute(stmt)
            old_price = p_res.scalar_one_or_none()
            return float(old_price) if old_price else 0.0
    except Exception:
        return 0.0

async def _get_historical_change(ticker: str, current_price: float) -> float:
    """
    Compute an approximate 24-hour percentage change from persisted prices.

    Inputs are the normalized ticker and current price; the output is a percent
    delta or 0.0 when the database lacks a suitable basis row.
    """
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Asset.id).where(Asset.ticker == ticker))
            a_id = res.scalar_one_or_none()
            if not a_id: return 0.0
            
            one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
            stmt = (
                select(PriceHistory.price)
                .where(PriceHistory.asset_id == a_id)
                .where(PriceHistory.timestamp <= one_day_ago)
                .order_by(desc(PriceHistory.timestamp))
                .limit(1)
            )
            p_res = await session.execute(stmt)
            old_price = p_res.scalar_one_or_none()
            if old_price and float(old_price) > 0:
                return ((current_price - float(old_price)) / float(old_price)) * 100.0
    except Exception as e:
        logger.warning(f"Historical change computation failed for {ticker}: {e}")
    return 0.0

@router.get("/history/{ticker:path}")
async def get_market_history(ticker: str, limit: int = 100):
    """
    Return the latest N persisted price points for one asset.

    The chart uses this database-backed history to provide context around the
    latest cache tick without depending on browser-only state.
    """
    try:
        t_upper = normalize_symbol(ticker)
        async with AsyncSessionLocal() as session:
            # Resolve Asset ID
            asset_res = await session.execute(select(Asset.id).where(Asset.ticker == t_upper))
            asset_id = asset_res.scalar_one_or_none()
            
            if not asset_id:
                raise HTTPException(status_code=404, detail=f"Asset {t_upper} not found.")

            # Fetch history
            stmt = (
                select(PriceHistory.timestamp, PriceHistory.price, PriceHistory.volume, PriceHistory.provider)
                .where(PriceHistory.asset_id == asset_id)
                .order_by(desc(PriceHistory.timestamp))
                .limit(limit)
            )
            res = await session.execute(stmt)
            history = res.all()
            
            # Return in chronological order for the chart
            return [
                {
                    "timestamp": h.timestamp.isoformat(),
                    "price": float(h.price),
                    "volume": float(h.volume) if h.volume else 0.0,
                    "provider": h.provider
                } for h in reversed(history)
            ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_market_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/control/start-ingestion")
async def start_market_stream(background_tasks: BackgroundTasks):
    """Start the market ingestion loop as a FastAPI background task."""
    if market_ingester.is_running:
        return {"status": "Ignored", "detail": "Ingestion is already running"}
    background_tasks.add_task(market_ingester.start_streaming)
    return {"status": "Started", "detail": "Market stream background task initiated."}

@router.post("/control/stop-ingestion")
async def stop_market_stream():
    """Request a graceful stop for the market ingestion loop."""
    market_ingester.stop()
    return {"status": "Stopped", "detail": "Market stream gracefully halted."}

@router.post("/inject")
async def inject_market_tick(tick: dict):
    """
    Inject one market tick for controlled validation.

    Manual ticks are treated as INTERNAL_FALLBACK unless the caller supplies a
    different source, so tests do not masquerade as live provider data.
    """
    await market_ingester.publish_tick(
        symbol=tick.get("symbol"),
        price=tick.get("price"),
        source=tick.get("source", "INTERNAL_FALLBACK")
    )
    return {"status": "Injected", "symbol": tick.get("symbol"), "price": tick.get("price")}

@router.get("/source-health")
@router.get("/status/source-health")
async def get_market_source_health_alias():
    """
    Alias for /market/status/source-health for truth-aligned graduation requirements.
    """
    from app.services.ingestion.market_ingester import market_ingester
    try:
        await redis_bus.connect()
        cached = await redis_bus.get("market:source_health")
        if cached:
            parsed = json.loads(cached) if isinstance(cached, (str, bytes)) else cached
            if isinstance(parsed, dict) and parsed:
                return parsed
    except Exception:
        pass
    return await market_ingester.get_source_health()

@router.get("/credentials/health")
async def get_credentials_health():
    """
    Checks for presence of critical API keys and returns masked versions for audit.
    """
    from app.core.config import mask_key
    keys_to_check = {
        "ALPACA_API_KEY": settings.ALPACA_API_KEY,
        "ALPACA_SECRET_KEY": settings.ALPACA_SECRET_KEY,
        "EVENTREGISTRY_API_KEY": settings.EVENTREGISTRY_API_KEY,
        "MARKETAUX_API_KEY": settings.MARKETAUX_API_KEY,
        "TWELVEDATA_API_KEY": settings.TWELVEDATA_API_KEY,
        "POLYGON_API_KEY": settings.POLYGON_API_KEY,
        "COINGECKO_API_KEY": settings.COINGECKO_API_KEY
    }
    
    status = {}
    credentials = {}
    
    for name, val in keys_to_check.items():
        exists = "EXISTS" if (val and len(val) > 4) else "MISSING"
        status[name] = exists
        credentials[name] = {
            "status": exists,
            "masked": mask_key(val) if val else "****"
        }
        
    return {
        "status": status,
        "trading_mode": settings.TRADING_MODE,
        "credentials": credentials
    }

# Catch-all route must stay last so fixed routes such as /status/snapshot win.
@router.get("/{ticker:path}")
@router.get("/live/{ticker:path}")
async def get_live_asset_price(ticker: str):
    """
    Return the latest known price for one asset.

    The route reads cache first for current provider metadata and falls back to
    the database as delayed historical data when no hot tick is available.
    """
    normalized_ticker = ticker.lower().strip("/")
    if normalized_ticker.startswith("status/") or normalized_ticker == "source-health":
        raise HTTPException(status_code=404, detail=f"Asset {ticker.upper()} not found in database.")
        
    try:
        t_upper = normalize_symbol(ticker)
        
        # Cache reads preserve provider status and lag metadata from ingestion.
        tick = await performance_cache.get(f"latest:tick:{t_upper}")
        if tick:
            return {
                "ticker": t_upper,
                "latest_price": tick.get("price", 0.0),
                "source": "cache",
                "status": tick.get("status_label", "LIVE"),
                "provider": sanitize_provider_name(tick.get("provider")),
                "timestamp": datetime.fromtimestamp(tick.get("ingest_ts", time.time())).isoformat(),
                "lag_ms": tick.get("lag_ms", 0.0)
            }
            
        # Database fallback is explicitly returned as delayed historical data.
        async with AsyncSessionLocal() as session:
            asset_res = await session.execute(select(Asset.id).where(Asset.ticker == t_upper))
            asset_id = asset_res.scalar_one_or_none()
            if not asset_id:
                raise HTTPException(status_code=404, detail=f"Asset {t_upper} not found in database.")

            price_res = await session.execute(
                select(PriceHistory.price, PriceHistory.timestamp)
                .where(PriceHistory.asset_id == asset_id)
                .order_by(desc(PriceHistory.timestamp))
                .limit(1)
            )
            latest = price_res.all()
            if latest:
                p, ts = latest[0]
                
                # Warm the cache briefly so repeated dashboard reads do not
                # reopen the database for the same historical value.
                tick_data = {
                    "ticker": t_upper,
                    "price": float(p),
                    "source": "db",
                    "status_label": "DELAYED_DB",
                    "provider": "Historical DB",
                    "ingest_ts": ts.timestamp() if hasattr(ts, "timestamp") else time.time(),
                    "lag_ms": 0.0
                }
                await performance_cache.set(f"latest:tick:{t_upper}", tick_data, ttl=60)
                
                return {
                    "ticker": t_upper,
                    "latest_price": float(p),
                    "source": "db",
                    "status": "DELAYED_DB",
                    "provider": "Historical DB",
                    "timestamp": ts.isoformat()
                }

        raise HTTPException(status_code=404, detail=f"No price data available for {t_upper}.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_live_asset_price: {e}")
        raise HTTPException(status_code=500, detail=str(e))
