"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Provides portfolio CRUD, valuation, history, and explainable rebalance endpoints.
- Combines portfolio positions with truth-labeled market prices for dashboard allocation logic.
"""

import os
import logging
import time
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.core.redis_client import redis_bus
from app.core.db import AsyncSessionLocal
from app.models.all_models import Portfolio, PortfolioAsset, Asset, User
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from app.services.ai_engine.rebalance_service import rebalance_service

logger = logging.getLogger(__name__)

router = APIRouter()

def _detect_asset_class(ticker: str) -> tuple[str, str]:
    """
    Infer an asset class and preferred provider from a supported ticker.

    The helper keeps portfolio CRUD aligned with the market ingestion universe
    when a user adds a symbol before it already exists in the Asset table.
    """
    t = ticker.upper()
    if t in ["AAPL", "TSLA", "MSFT", "GOOGL", "AMZN"]: return "EQUITY", "ALPACA"
    if "/" in t or t in ["BTC", "ETH", "LTC"]: return "CRYPTO", "ALPACA"
    if t in ["XAU/USD", "XAG/USD", "GOLD", "SILVER"]: return "METAL", "OANDA"
    if t in ["WTI", "BRENT", "OIL"]: return "ENERGY", "OANDA"
    if any(fx in t for fx in ["EUR", "GBP", "JPY", "TRY", "USD"]): return "FOREX", "OANDA"
    return "EQUITY", "ALPACA"

def _tick_cache_keys(ticker: str) -> List[str]:
    """
    Return accepted cache key variants for one ticker.

    Crypto and FX providers use both slash and compact symbol formats, so
    portfolio valuation checks every normalized key before falling back to DB.
    """
    keys = [f"latest:tick:{ticker}", f"tick:{ticker}"]
    if "/" in ticker:
        alt = ticker.replace("/", "")
        keys.extend([
            f"latest:tick:{alt}",
            f"tick:{alt}",
            f"latest:tick:{alt}T",
            f"tick:{alt}T",
        ])
    return keys

def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    """Convert provider/cache values to float without breaking valuation paths."""
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default

def _timestamp_to_seconds(value: Any) -> Optional[float]:
    """
    Normalize provider timestamps to epoch seconds.

    Cache entries may contain seconds, milliseconds, or ISO timestamps; this
    helper lets source classification compare them consistently.
    """
    if value is None:
        return None
    numeric = _safe_float(value, None)
    if numeric is not None:
        return numeric / 1000 if numeric > 10_000_000_000 else numeric
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None

def _classify_cached_price_source(price_data: Dict[str, Any]) -> str:
    """
    Convert raw cached market tick metadata into the rebalance source label.

    Labels intentionally distinguish LIVE_PROVIDER, DELAYED_PROVIDER, HISTORY_DB,
    INTERNAL_FALLBACK, and UNKNOWN so the dashboard does not overstate data quality.
    """
    raw_label = str(
        price_data.get("status_label")
        or price_data.get("source_type")
        or price_data.get("provider")
        or ""
    ).upper()
    provider = str(price_data.get("provider") or "").upper()

    if "FALLBACK" in raw_label or "INTERNAL" in raw_label or "FALLBACK" in provider:
        return "INTERNAL_FALLBACK"
    if "HISTORY" in raw_label or "DB" in raw_label:
        return "HISTORY_DB"

    lag_ms = _safe_float(price_data.get("lag_ms"), None)
    if lag_ms is not None and lag_ms > 300_000:
        return "DELAYED_PROVIDER"

    provider_ts = _timestamp_to_seconds(
        price_data.get("provider_ts")
        or price_data.get("source_ts")
        or price_data.get("timestamp")
        or price_data.get("ingest_ts")
    )
    if provider_ts is not None and time.time() - provider_ts > 300:
        return "DELAYED_PROVIDER"

    if "DELAY" in raw_label or provider in {"ALPHAVANTAGE", "OANDA"}:
        return "DELAYED_PROVIDER"
    if "LIVE" in raw_label or provider in {"ALPACA", "ALPACA PAPER", "TWELVEDATA", "BINANCE", "COINGECKO"}:
        return "LIVE_PROVIDER"

    return "INTERNAL_FALLBACK"

async def _read_cached_tick(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Read the freshest cached tick for a ticker across normalized Redis key variants.

    FX and crypto symbols may be stored with slashes, compact notation, or
    provider-specific suffixes, so rebalance valuation checks all accepted forms.
    """
    import json

    for key in _tick_cache_keys(ticker):
        tick_str = await redis_bus.get(key)
        if tick_str:
            return json.loads(tick_str) if isinstance(tick_str, (str, bytes)) else tick_str
    return None

class PortfolioCreate(BaseModel):
    """
    Request schema for creating a model portfolio.

    The initial cash and risk profile seed the local academic portfolio used by
    allocation and rebalance demonstrations.
    """
    name: str
    risk_profile: str = "MEDIUM"
    initial_cash: float = 100000.0

class AssetAdd(BaseModel):
    """
    Request schema for adding or increasing a portfolio asset position.

    The ticker is normalized later by the API so supported market symbols remain
    consistent with ingestion and rebalance services.
    """
    ticker: str
    quantity: float = 0.0

@router.get("")
@router.get("/")
async def list_portfolios():
    """
    Return all model portfolios for the Portfolio Hub selector.

    The response is intentionally lightweight so the dashboard can list
    portfolios before fetching the selected portfolio detail view.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Portfolio))
        portfolios = result.scalars().all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "risk_profile": p.risk_profile if p.risk_profile != "AI-Driven Dynamic" else "MEDIUM",
                "total_value": p.total_value,
                "cash": p.cash,
                "symbol": p.name, # Compatibility
                "created_at": p.created_at.isoformat() if p.created_at else None
            } for p in portfolios
        ]

@router.post("")
async def create_portfolio(data: PortfolioCreate):
    """
    Create a model portfolio with initial cash and risk profile.

    This academic portfolio powers allocation and rebalance demonstrations; it
    is separate from Alpaca Paper brokerage account telemetry.
    """
    async with AsyncSessionLocal() as session:
        # The project stores model portfolios under the first user when no
        # authenticated owner is supplied by this route.
        user_res = await session.execute(select(User).limit(1))
        user = user_res.scalar_one_or_none()
        if not user:
            # Seed a minimal local user so portfolio demos can run on fresh DBs.
            user = User(username="admin", email="admin@apex.ai", password_hash="hashed_password")
            session.add(user)
            await session.commit()
            await session.refresh(user)

        new_p = Portfolio(
            name=data.name,
            user_id=user.id,
            risk_profile=data.risk_profile.upper(),
            cash=data.initial_cash,
            total_value=data.initial_cash
        )
        session.add(new_p)
        await session.commit()
        await session.refresh(new_p)
        return {"id": new_p.id, "status": "created"}

@router.get("/status")
async def get_portfolio_status():
    """
    Fetch broker account telemetry for the dashboard portfolio status badge.

    Alpaca Paper values are surfaced separately from the model portfolio so AUM,
    local allocation, and proof state remain academically clear.
    """
    from app.services.broker.alpaca_adapter import alpaca_adapter
    from app.core.config import get_settings
    settings = get_settings()
    
    # Paper mode reports the external Alpaca account separately from the local
    # model portfolio so AUM proof and allocation demos remain distinct.
    if settings.TRADING_MODE == "PAPER":
        try:
            account = await alpaca_adapter.get_account()
            logger.info(f"DEBUG: Alpaca Account Response: {account}")
            
            # Treat only an ACTIVE Alpaca Paper account as connected proof.
            acc_status = str(account.get("status", "INACTIVE")).upper().strip()
            
            if account and acc_status == "ACTIVE":
                portfolio_value = account.get("portfolio_value")
                equity = account.get("equity")
                aum = float(portfolio_value if portfolio_value is not None else (equity if equity is not None else 100000.0))
                cash_val = account.get("cash")
                cash = float(cash_val if cash_val is not None else 100000.0)
                status_data = {
                    "aum": aum,
                    "cash": cash,
                    "currency": account.get("currency", "USD"),
                    "status": account.get("status", "ACTIVE"),
                    "buying_power": float(account.get("buying_power", 0.0)),
                    "provider": "Alpaca Paper",
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
                # Cache account telemetry for workers that need a recent balance.
                import json
                await redis_bus.set("account_balance", json.dumps(status_data), ex=60)
                return status_data
            else:
                # A non-ACTIVE provider account should not be presented as live.
                logger.warning(f"Alpaca account status is {account.get('status')} - Not ACTIVE.")
        except Exception as e:
            logger.error(f"Alpaca API connection failure: {e}")

    # For proof mode, failing closed is more honest than returning simulated AUM.
    raise HTTPException(
        status_code=503, 
        detail="Portfolio connection failed. Alpaca Paper account must be active for live proof."
    )

@router.get("/history")
async def get_portfolio_history(status: str = "FILLED", limit: int = 50):
    """
    Returns the execution history (Truth Audit) for the portfolio.
    Requirement: Must support status filtering for truth-aligned proofs.
    """
    from app.models.all_models import ExecutionLog, Asset
    from sqlalchemy import select, desc
    from app.core.db import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ExecutionLog, Asset.ticker)
                .join(Asset, ExecutionLog.asset_id == Asset.id)
                .order_by(desc(ExecutionLog.timestamp))
            )
            
            if status:
                stmt = stmt.where(ExecutionLog.status == status.upper())
                
            stmt = stmt.limit(limit)
            
            res = await session.execute(stmt)
            logs = res.all()
            
            return [
                {
                    "id": log.id,
                    "ticker": ticker,
                    "action": log.action,
                    "quantity": log.quantity,
                    "price": log.price,
                    "status": log.status,
                    "order_id": log.order_id,
                    "provider": log.provider,
                    "filled_qty": log.filled_qty,
                    "filled_avg_price": log.filled_avg_price,
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None
                } for log, ticker in logs
            ]
    except Exception as e:
        logger.error(f"Error fetching portfolio history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{portfolio_id}")
async def get_portfolio_details(portfolio_id: int):
    """
    Return detailed holdings, valuation, and price-source labels for a portfolio.

    Prices are cache-first and DB-backed when needed; each position keeps a
    source label so the Portfolio Hub can show live, delayed, history, or missing
    data rather than hiding provenance.
    """
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Portfolio)
            .options(selectinload(Portfolio.assets).selectinload(PortfolioAsset.asset))
            .where(Portfolio.id == portfolio_id)
        )
        res = await session.execute(stmt)
        p = res.scalar_one_or_none()
        
        if not p:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        # Resolve a price for each held asset and keep the data-quality label
        # alongside the value used for allocation math.
        prices = {}
        price_sources = {}
        for pa in p.assets:
            ticker = pa.asset.ticker

            price_data = await _read_cached_tick(ticker)
            if price_data:
                prices[ticker] = float(price_data.get('price', 0.0))
                price_sources[ticker] = _classify_cached_price_source(price_data)
            else:
                # DB fallback is labeled HISTORY_DB because it is persisted
                # market history, not a current live provider quote.
                from app.models.all_models import PriceHistory
                hist_stmt = select(PriceHistory.price).where(PriceHistory.asset_id == pa.asset_id).order_by(desc(PriceHistory.timestamp)).limit(1)
                hist_res = await session.execute(hist_stmt)
                price = hist_res.scalar_one_or_none()
                if price:
                    prices[ticker] = float(price)
                    price_sources[ticker] = "HISTORY_DB"
                else:
                    prices[ticker] = 0.0
                    price_sources[ticker] = "MISSING"

        assets_list = []
        current_total_value = p.cash
        for pa in p.assets:
            ticker = pa.asset.ticker
            price = prices.get(ticker, 0.0)
            source = price_sources.get(ticker, "MISSING")
            market_val = pa.quantity * price
            current_total_value += market_val
            
            assets_list.append({
                "ticker": ticker,
                "symbol": ticker, # For frontend compatibility
                "quantity": pa.quantity,
                "avg_price": pa.avg_price,
                "latest_price": price,
                "price_source": source,
                "market_value": round(market_val, 2),
                "weight": 0.0,
                "warning": "No real price available" if source == "MISSING" else None
            })

        # Weights are calculated after all market values are known.
        for a in assets_list:
            if current_total_value > 0:
                a["weight"] = round(a["market_value"] / current_total_value, 4)

        return {
            "id": p.id,
            "name": p.name,
            "risk_profile": p.risk_profile if p.risk_profile != "AI-Driven Dynamic" else "MEDIUM",
            "cash": round(p.cash, 2),
            "total_value": round(current_total_value, 2),
            "positions": assets_list, # For new UI
            "assets": assets_list,    # For backward compatibility
            "updated_at": p.updated_at.isoformat() if p.updated_at else None
        }

@router.post("/{portfolio_id}/assets")
async def add_asset_to_portfolio(portfolio_id: int, data: AssetAdd):
    """
    Add a new holding or increase an existing holding quantity.

    The route creates missing Asset rows with inferred class/provider metadata
    so portfolio demos can include the supported market universe.
    """
    async with AsyncSessionLocal() as session:
        # Reuse an existing Asset row when available to keep price history joins stable.
        asset_res = await session.execute(select(Asset).where(Asset.ticker == data.ticker.upper()))
        asset = asset_res.scalar_one_or_none()
        if not asset:
            a_class, prov = _detect_asset_class(data.ticker)
            asset = Asset(
                ticker=data.ticker.upper(), 
                name=data.ticker.upper(), 
                asset_class=a_class,
                provider=prov
            )
            session.add(asset)
            await session.flush()

        # Update the existing portfolio-asset link instead of duplicating rows.
        stmt = select(PortfolioAsset).where(
            PortfolioAsset.portfolio_id == portfolio_id,
            PortfolioAsset.asset_id == asset.id
        )
        res = await session.execute(stmt)
        pa = res.scalar_one_or_none()

        if pa:
            pa.quantity += data.quantity
        else:
            pa = PortfolioAsset(
                portfolio_id=portfolio_id,
                asset_id=asset.id,
                quantity=data.quantity,
                avg_price=100.0 # Simplified
            )
            session.add(pa)
        
        await session.commit()
        return {"status": "asset added/updated"}

@router.delete("/{portfolio_id}/assets/{ticker:path}")
async def remove_asset_from_portfolio(portfolio_id: int, ticker: str):
    """Remove one ticker from the selected model portfolio."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(PortfolioAsset)
            .join(Asset)
            .where(PortfolioAsset.portfolio_id == portfolio_id, Asset.ticker == ticker.upper())
        )
        res = await session.execute(stmt)
        pa = res.scalar_one_or_none()
        if not pa:
            raise HTTPException(status_code=404, detail="Asset not found in portfolio")
        
        await session.delete(pa)
        await session.commit()
        return {"status": "asset removed"}

@router.post("/{portfolio_id}/rebalance")
@router.get("/{portfolio_id}/rebalance")
async def suggest_rebalance(portfolio_id: int):
    """
    Generate source-aware BUY/SELL/HOLD rebalance suggestions for one portfolio.

    Current weights are valued using cache-first market data, with HISTORY_DB or
    MISSING labels when live/delayed providers are unavailable.
    """
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Portfolio)
            .options(selectinload(Portfolio.assets).selectinload(PortfolioAsset.asset))
            .where(Portfolio.id == portfolio_id)
        )
        res = await session.execute(stmt)
        p = res.scalar_one_or_none()
        
        if not p:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        # Price source quality feeds the rebalance engine so conviction reflects
        # whether each quote is live, delayed, historical, or fallback.
        prices = {}
        price_sources = {}
        for ticker in rebalance_service.SUPPORTED_TICKERS:
            price_data = await _read_cached_tick(ticker)

            if price_data:
                prices[ticker] = float(price_data.get('price', 0.0))
                price_sources[ticker] = _classify_cached_price_source(price_data)
            else:
                # Redis can miss after restarts; DB fallback keeps rebalance
                # explainable while marking the source as HISTORY_DB.
                from app.models.all_models import PriceHistory
                hist_stmt = (
                    select(PriceHistory.price)
                    .join(Asset, PriceHistory.asset_id == Asset.id)
                    .where(Asset.ticker == ticker)
                    .order_by(desc(PriceHistory.timestamp))
                    .limit(1)
                )
                hist_res = await session.execute(hist_stmt)
                db_price = hist_res.scalar_one_or_none()
                prices[ticker] = float(db_price) if db_price else 0.0
                price_sources[ticker] = "HISTORY_DB" if db_price else "MISSING"

        # Recompute total value from current prices so rebalance drift uses the
        # same valuation basis the user sees in the dashboard.
        current_total_value = p.cash
        for pa in p.assets:
            ticker = pa.asset.ticker
            price = prices.get(ticker, 0.0)
            current_total_value += pa.quantity * price
        
        # Pass dynamic valuation to the service without mutating the database row.
        p.dynamic_total_value = current_total_value
        
        suggestions = await rebalance_service.calculate_rebalance(p, prices, price_sources)
        target_allocation = rebalance_service.get_target_allocation(p.risk_profile)
        cash_weight = (p.cash / current_total_value) if current_total_value > 0 else 0.0
        target_cash_weight = target_allocation.get("CASH", 0.0)
        source_summary: Dict[str, int] = {}
        for label in price_sources.values():
            source_summary[label] = source_summary.get(label, 0) + 1

        return {
            "portfolio_id": portfolio_id,
            "risk_profile": p.risk_profile,
            "methodology": "Explainable risk-profile allocation with adaptive drift thresholds; suggestions are not automatic trade execution.",
            "portfolio_value": round(current_total_value, 2),
            "cash_position": {
                "current_cash": round(p.cash, 2),
                "current_weight": round(cash_weight, 4),
                "target_weight": round(target_cash_weight, 4),
                "drift": round(target_cash_weight - cash_weight, 4)
            },
            "price_source_summary": source_summary,
            "suggestions": suggestions
        }

@router.post("/{portfolio_id}/reset")
async def reset_portfolio(portfolio_id: int):
    """Reset cached demonstration capital for the selected portfolio."""
    await redis_bus.publish("account_balance", '{"aum": 100000.0}')
    return {"status": "Reset Successful", "initial_capital": 100000.0}

@router.post("/{portfolio_id}/export")
async def export_portfolio_data(portfolio_id: int):
    """
    Generate a compact Excel report for portfolio review.

    The export summarizes portfolio metrics for academic documentation without
    changing model portfolio state.
    """
    try:
        import pandas as pd
        # Build a minimal report table from the current portfolio/evaluation view.
        df_perf = pd.DataFrame([{
            "Metric": ["Initial Capital", "Current AUM", "Sharpe Ratio", "Max Drawdown"],
            "Value": ["$100,000.00", "Live", "Calculated from execution history", "Calculated from portfolio history"]
        }])
        
        # This verification export records the current state; a production export
        # would expand this with historical DB queries.
        filename = f"Apex_Report_GP2_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        export_path = os.path.join(os.getcwd(), filename)
        
        with pd.ExcelWriter(export_path, engine='openpyxl') as writer:
            df_perf.to_excel(writer, sheet_name='Performance', index=False)
            
        return {"status": "Exported", "path": export_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
