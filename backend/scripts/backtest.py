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
import json
import os
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
INITIAL_CAPITAL = 100000.0
SIM_HOLDINGS = {} # ticker: quantity
SIM_CASH = INITIAL_CAPITAL

async def run_backtest_iteration():
    global SIM_CASH, SIM_HOLDINGS
    
    print(f"\n--- [BACKTEST SIMULATION] {datetime.now().isoformat()} ---")
    
    # Check if we are in local TEST_MODE (Internal Services direct call)
    if os.getenv("TEST_MODE") == "1":
        print("[MODE] LOCAL TEST_MODE (In-memory simulation)")
        from app.services.ai_engine.recommender import recommender_service
        from app.services.cache_service import performance_cache
        from app.models.all_models import Asset
        from app.core.db import AsyncSessionLocal
        from sqlalchemy import select
        
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Asset))
            assets = res.scalars().all()
            
            for asset in assets:
                cache_key = f"latest:tick:{asset.ticker}"
                tick = await performance_cache.get(cache_key)
                price = tick["price"] if tick else 50000.0
                
                rec = await recommender_service.generate_recommendation(asset.id)
                action = rec["action"]
                
                print(f"SIGNAL: {asset.ticker} -> {action} @ ${price:,.2f}")
                
                # Local Ledger Simulation
                if action == "BUY" and SIM_CASH > (price * 0.1):
                    buy_amt = SIM_CASH * 0.1
                    qty = buy_amt / price
                    SIM_CASH -= buy_amt
                    SIM_HOLDINGS[asset.ticker] = SIM_HOLDINGS.get(asset.ticker, 0.0) + qty
                    print(f"   [EXECUTED] Bought {qty:.4f} {asset.ticker}")
                elif action == "SELL" and SIM_HOLDINGS.get(asset.ticker, 0.0) > 0:
                    qty = SIM_HOLDINGS[asset.ticker]
                    sell_val = qty * price
                    SIM_CASH += sell_val
                    SIM_HOLDINGS[asset.ticker] = 0.0
                    print(f"   [EXECUTED] Sold {qty:.4f} {asset.ticker}")

    else:
        # LIVE / PAPER mode (via API endpoints)
        from app.core.config import get_settings
        settings = get_settings()
        
        print(f"[MODE] EXTERNAL API MODE (Trading: {settings.TRADING_MODE})")
        
        async with httpx.AsyncClient() as client:
            try:
                print("Fetching AI Recommendations...")
                resp = await client.get(f"{BASE_URL}/ai/recommendations/latest")
                if resp.status_code != 200:
                    print(f"Error fetching recommendations: {resp.status_code}")
                    return
                
                recommendations = resp.json()
                
                for rec in recommendations:
                    ticker = rec["ticker"]
                    action = rec["action"]
                    
                    price_resp = await client.get(f"{BASE_URL}/market/{ticker}")
                    price = price_resp.json().get("latest_price", 0.0) if price_resp.status_code == 200 else 0.0
                    if price == 0: continue
                    
                    print(f"SIGNAL: {ticker} -> {action} @ ${price:,.2f}")
                    
                    # BROKER EXECUTION (Alpaca Paper Trading)
                    if settings.TRADING_MODE == "PAPER" and settings.ALPACA_API_KEY:
                        from app.services.broker.alpaca_adapter import alpaca_adapter
                        print(f"   [ALPACA] Dispatching {action} order...")
                        try:
                            order = await alpaca_adapter.execute_order(ticker, 0.01 if "USDT" in ticker else 1, action)
                            if order:
                                print(f"   [ALPACA] Order ACK: {order.get('id')} ({order.get('status')})")
                        except Exception as e:
                            print(f"   [ALPACA] Order Failed: {e}")

                    # LOCAL SIMULATION (resilient Ledger)
                    if action == "BUY" and SIM_CASH > (price * 0.1):
                        buy_amt = SIM_CASH * 0.1
                        qty = buy_amt / price
                        SIM_CASH -= buy_amt
                        SIM_HOLDINGS[ticker] = SIM_HOLDINGS.get(ticker, 0.0) + qty
                    elif action == "SELL" and SIM_HOLDINGS.get(ticker, 0.0) > 0:
                        qty = SIM_HOLDINGS[ticker]
                        SIM_CASH += qty * price
                        SIM_HOLDINGS[ticker] = 0.0

            except Exception as e:
                print(f"Backtest API Error: {e}")
    
    # 3. Calculate Portfolio Value
    # (Portfolio value calculation remains similar, but in TEST_MODE we can use cache)
    total_value = SIM_CASH
    for t, q in SIM_HOLDINGS.items():
        if os.getenv("TEST_MODE") == "1":
            from app.services.cache_service import performance_cache
            tick = await performance_cache.get(f"latest:tick:{t}")
            p = tick["price"] if tick else 0.0
        else:
            async with httpx.AsyncClient() as client:
                p_resp = await client.get(f"{BASE_URL}/market/{t}")
                p = p_resp.json().get("latest_price", 0.0) if p_resp.status_code == 200 else 0.0
        total_value += q * p
    
    pnl = total_value - INITIAL_CAPITAL
    print(f"PORTFOLIO STATUS: AUM: ${total_value:,.2f} | PnL: ${pnl:,.2f} ({ (pnl/INITIAL_CAPITAL)*100:.2f}%)")

if __name__ == "__main__":
    # This script is intended to run while the server is active
    # For CI verification, it can be run once.
    asyncio.run(run_backtest_iteration())
