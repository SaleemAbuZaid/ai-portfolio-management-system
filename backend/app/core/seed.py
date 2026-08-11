"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Seeds baseline users, portfolios, assets, and proof-friendly data needed for local demonstration.
"""
import asyncio
import logging
import os
import secrets
import time
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy import select, insert, func

from app.core.db import AsyncSessionLocal
from app.models.all_models import User, Portfolio, Asset, PriceHistory, News, Sentiment
from app.core.auth_utils import get_password_hash

logger = logging.getLogger("Seed")

async def seed_database():
    """Bootstrap the database with initial records and historical data."""
    async with AsyncSessionLocal() as session:
        try:
            # 1. Create application users. Passwords come from environment
            # variables; missing values are replaced with non-disclosed random
            # values so the repository never ships shared login credentials.
            user_configs = [
                {"email": "admin@apex.local", "username": "admin", "role": "ADMIN", "full_name": "Apex Admin", "password": os.getenv("SEED_ADMIN_PASSWORD")},
                {"email": "broker@apex.local", "username": "broker", "role": "BROKER", "full_name": "Apex Broker", "password": os.getenv("SEED_BROKER_PASSWORD")},
                {"email": "user@apex.local", "username": "user", "role": "USER", "full_name": "Apex User", "password": os.getenv("SEED_USER_PASSWORD")},
                {"email": "system@apex.ai", "username": "system_user", "role": "ADMIN", "full_name": "System Administrator", "password": None},
            ]
            
            for cfg in user_configs:
                user_stmt = select(User).where((User.email == cfg["email"]) | (User.username == cfg["username"]))
                result = await session.execute(user_stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    raw_password = cfg["password"] or secrets.token_urlsafe(32)
                    user = User(
                        username=cfg["username"],
                        email=cfg["email"],
                        password_hash=get_password_hash(raw_password),
                        role=cfg["role"],
                        full_name=cfg["full_name"],
                        is_active=True
                    )
                    session.add(user)
                    await session.flush()
                    logger.info(f"Seed: Created user {cfg['email']} with role {cfg['role']}")
                else:
                    # Update existing user
                    user.username = cfg["username"]
                    user.role = cfg["role"]
                    user.full_name = cfg["full_name"]
                    user.email = cfg["email"]
                    if cfg["password"]:
                        user.password_hash = get_password_hash(cfg["password"])
                    logger.info(f"Seed: Updated existing user {cfg['username']} (now {cfg['email']}) to role {cfg['role']}")

            # Get system user for backward compatibility with portfolios
            result = await session.execute(select(User).where(User.email == "system@apex.ai"))
            user = result.scalar_one()
            
            # 2. Create System Portfolios (Requirement 1)
            risk_profiles = ["HIGH", "MEDIUM", "LOW"]
            for rp in risk_profiles:
                p_name = f"{rp.capitalize()} Risk Portfolio"
                p_stmt = select(Portfolio).where(Portfolio.name == p_name).limit(1)
                p_result = await session.execute(p_stmt)
                existing_p = p_result.scalars().first()
                
                if not existing_p:
                    new_p = Portfolio(
                        user_id=user.id,
                        name=p_name,
                        risk_profile=rp,
                        cash=100000.0,
                        total_value=100000.0
                    )
                    session.add(new_p)
                    await session.flush()
                    logger.info(f"Seed: Created {p_name}.")
                
            # Default portfolio reference for seeding assets if needed
            portfolio_stmt = select(Portfolio).where(Portfolio.user_id == user.id).limit(1)
            result = await session.execute(portfolio_stmt)
            portfolio = result.scalars().first()
                
            # 3. Create All 12 Assets
            assets_to_seed = [
                {"ticker": "AAPL", "name": "Apple Inc.", "asset_class": "EQUITY", "default_price": 230.20},
                {"ticker": "TSLA", "name": "Tesla Inc.", "asset_class": "EQUITY", "default_price": 180.50},
                {"ticker": "BTC/USD", "name": "Bitcoin", "asset_class": "CRYPTO", "default_price": 74000.0},
                {"ticker": "ETH/USD", "name": "Ethereum", "asset_class": "CRYPTO", "default_price": 2250.0},
                {"ticker": "EUR/USD", "name": "Euro / US Dollar", "asset_class": "FX", "default_price": 1.085},
                {"ticker": "GBP/USD", "name": "British Pound / US Dollar", "asset_class": "FX", "default_price": 1.250},
                {"ticker": "USD/TRY", "name": "US Dollar / Turkish Lira", "asset_class": "FX", "default_price": 32.50},
                {"ticker": "USD/JPY", "name": "US Dollar / Japanese Yen", "asset_class": "FX", "default_price": 155.00},
                {"ticker": "XAU/USD", "name": "Gold / US Dollar", "asset_class": "COMMODITY", "default_price": 2350.0},
                {"ticker": "XAG/USD", "name": "Silver / US Dollar", "asset_class": "COMMODITY", "default_price": 28.50},
                {"ticker": "WTI", "name": "WTI Crude Oil", "asset_class": "COMMODITY", "default_price": 82.00},
                {"ticker": "BRENT", "name": "Brent Crude Oil", "asset_class": "COMMODITY", "default_price": 86.00},
            ]
            
            asset_map = {}
            for asset_data in assets_to_seed:
                default_price = asset_data.pop("default_price")
                ticker = asset_data["ticker"]
                asset_stmt = select(Asset).where(Asset.ticker == ticker).limit(1)
                result = await session.execute(asset_stmt)
                existing_asset = result.scalars().first()
                
                if not existing_asset:
                    new_asset = Asset(**asset_data)
                    session.add(new_asset)
                    await session.flush()
                    logger.info(f"Seed: Created asset {ticker}")
                    asset_id_to_seed = new_asset.id
                else:
                    asset_id_to_seed = existing_asset.id
                    
                asset_map[ticker] = asset_id_to_seed
                # Also map common aliases
                aliases = {
                    "BTCUSDT": "BTC/USD", "ETHUSDT": "ETH/USD",
                    "XAUUSD": "XAU/USD", "XAGUSD": "XAG/USD",
                    "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD",
                    "USDTRY": "USD/TRY", "USDJPY": "USD/JPY"
                }
                for alias, true_ticker in aliases.items():
                    if true_ticker == ticker:
                        asset_map[alias] = asset_id_to_seed

            await session.commit()

            # Ensure Portfolios exist (Phase 1 Requirement)
            portfolio_configs = [
                {"name": "System Portfolio", "risk_profile": "MEDIUM"},
                {"name": "High Risk Portfolio", "risk_profile": "HIGH"},
                {"name": "Medium Risk Portfolio", "risk_profile": "MEDIUM"},
                {"name": "Low Risk Portfolio", "risk_profile": "LOW"}
            ]
            
            for p_cfg in portfolio_configs:
                p_stmt = select(Portfolio).where(Portfolio.name == p_cfg["name"]).limit(1)
                p_res = await session.execute(p_stmt)
                if not p_res.scalar_one_or_none():
                    new_p = Portfolio(
                        name=p_cfg["name"], 
                        user_id=user.id,
                        risk_profile=p_cfg["risk_profile"], 
                        cash=100000.0,
                        total_value=100000.0
                    )
                    session.add(new_p)
                    logger.info(f"Seed: Created portfolio {p_cfg['name']}")
            
            await session.commit()

            # 3.5 Seed Assets into Portfolios (Phase 1 Requirement)
            from app.models.all_models import PortfolioAsset
            portfolio_seed_configs = {
                "System Portfolio": ["AAPL", "TSLA", "BTC/USD"],
                "High Risk Portfolio": ["BTC/USD", "ETH/USD", "TSLA", "AAPL"],
                "Medium Risk Portfolio": ["AAPL", "BTC/USD", "XAU/USD", "EUR/USD", "WTI"],
                "Low Risk Portfolio": ["XAU/USD", "XAG/USD", "EUR/USD", "USD/JPY", "BRENT"]
            }
            
            for p_name, tickers in portfolio_seed_configs.items():
                p_stmt = select(Portfolio).where(Portfolio.name == p_name).limit(1)
                p_res = await session.execute(p_stmt)
                p = p_res.scalar_one_or_none()
                if p:
                    for ticker in tickers:
                        aid = asset_map.get(ticker)
                        if aid:
                            # Check if asset already exists in portfolio
                            pa_stmt = select(PortfolioAsset).where(
                                PortfolioAsset.portfolio_id == p.id,
                                PortfolioAsset.asset_id == aid
                            )
                            pa_res = await session.execute(pa_stmt)
                            if not pa_res.scalar_one_or_none():
                                pa = PortfolioAsset(
                                    portfolio_id=p.id,
                                    asset_id=aid,
                                    quantity=1.0, # Default seed quantity
                                    avg_price=100.0
                                )
                                session.add(pa)
                                logger.info(f"Seed: Added {ticker} to {p_name}")
            
            await session.commit()

            # 4. Check existing PriceHistory
            count_stmt = select(func.count(PriceHistory.timestamp))
            result = await session.execute(count_stmt)
            total_history_rows = result.scalar()

            if total_history_rows < 1000:
                logger.info(f"PriceHistory has {total_history_rows} rows. Loading real historical data...")
                
                # Look for data file (paths inside docker context)
                data_path = "/app/data/training/market_training_long.parquet"
                if not os.path.exists(data_path):
                    data_path = "/app/data/training/market_training_long.csv"
                    if not os.path.exists(data_path):
                        data_path = "data/training/market_training_long.parquet"
                        if not os.path.exists(data_path):
                            data_path = "data/training/market_training_long.csv"

                if os.path.exists(data_path):
                    try:
                        logger.info(f"Loading data from {data_path}...")
                        if data_path.endswith('.parquet'):
                            df = pd.read_parquet(data_path)
                        else:
                            df = pd.read_csv(data_path)
                            
                        # Format DataFrame for insertion
                        records = []
                        valid_count = 0
                        
                        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
                        
                        for row in df.itertuples(index=False):
                            symbol = getattr(row, 'symbol', None)
                            if not symbol:
                                continue
                            
                            # Resolve symbol to asset_id
                            asset_id = asset_map.get(symbol)
                            if not asset_id:
                                continue
                                
                            ts = getattr(row, 'timestamp', None)
                            price = getattr(row, 'close', None)
                            if pd.isna(price) or pd.isna(ts):
                                continue
                                
                            volume = getattr(row, 'volume', 0.0)
                            if pd.isna(volume): volume = 0.0
                            
                            records.append({
                                "asset_id": asset_id,
                                "timestamp": ts,
                                "price": float(price),
                                "volume": float(volume),
                                "provider": "historical_seed",
                                "provider_ts": ts.timestamp(),
                                "ingest_ts": time.time(),
                                "lag_ms": 0.0
                            })
                            valid_count += 1
                            
                            # Batch insert every 10k rows
                            if len(records) >= 10000:
                                await session.execute(insert(PriceHistory), records)
                                await session.commit()
                                records = []
                                
                        if records:
                            await session.execute(insert(PriceHistory), records)
                            
                        await session.commit()
                        logger.info(f"Successfully loaded {valid_count} historical price rows.")
                    except Exception as e:
                        logger.error(f"Error loading historical data: {e}")
                        await session.rollback()
                else:
                    logger.warning("No historical data file found. Falling back to default initial prices.")
                    # Fallback to single row insertion
                    for asset_data in assets_to_seed:
                        ticker = asset_data["ticker"]
                        aid = asset_map[ticker]
                        
                        price_stmt = select(PriceHistory).where(PriceHistory.asset_id == aid).limit(1)
                        result_price = await session.execute(price_stmt)
                        if not result_price.scalars().first():
                            ph = PriceHistory(
                                asset_id=aid,
                                price=200.0,
                                provider="initial_bootstrap",
                                timestamp=datetime.now(timezone.utc)
                            )
                            session.add(ph)
                    await session.commit()
            else:
                logger.info(f"PriceHistory already has {total_history_rows} rows. Skipping load.")

            # 5. Seed Initial News
            news_stmt = select(News).where(News.article_id == "initial_bootstrap_news").limit(1)
            result_news = await session.execute(news_stmt)
            if not result_news.scalars().first():
                news_item = News(
                    article_id="initial_bootstrap_news",
                    provider="system",
                    headline="Market analysis indicates high liquidity for major indices.",
                    url="https://verify.apex.ai/bootstrap",
                    published_at=datetime.now(timezone.utc),
                    ingest_ts=time.time()
                )
                session.add(news_item)
                await session.flush()
                
                # Associated Sentiment
                sentiment = Sentiment(
                    news_id=news_item.id,
                    asset_id=None,
                    score=0.1,
                    label="NEUTRAL"
                )
                session.add(sentiment)
                await session.commit()
                logger.info("Seed: Created initial news record.")
            
            logger.info("Bootstrap Data: COMPLETED")
        except Exception as e:
            logger.error(f"Bootstrap Data Failed: {e}")
            await session.rollback()

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_database())
