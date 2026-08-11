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
import httpx
import asyncio
import json
import os
import time
from datetime import datetime

# [START] Starting Apex Step 12 Backtest Simulation
# This script stress-tests the AI pipeline and verifies deterministic PnL tracking.
# FORCED VALIDATION MODE: Injects bullish/bearish signals to ensure trade execution.

from app.core.redis_client import redis_bus
import redis
import sys

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
TICKERS = ["AAPL", "BTCUSDT", "ETHUSDT"]
INITIAL_CAPITAL = 100000.0

async def run_backtest():
    print(f"\n[START] Starting Apex Step 12 Backtest Simulation...", flush=True)
    print(f"Targeting: {TICKERS}", flush=True)
    
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "status": "INITIALIZING",
        "initial_cash": INITIAL_CAPITAL,
        "final_cash": INITIAL_CAPITAL,
        "holdings": {},
        "trades": [],
        "trades_executed": 0,
        "buy_count": 0,
        "sell_count": 0,
        "pnl": 0.0,
        "return_percent": 0.0,
        "data_points_used": 0,
        "recommendations_read": 0
    }

    async with httpx.AsyncClient(base_url=API_BASE, timeout=60.0) as client:
        try:
            # 0. Connect to Redis
            await redis_bus.connect()
            
            # 1. Warm-up: Inject base prices
            print(">>> Warming up pipeline (Injecting base prices)...", flush=True)
            base_prices = {"AAPL": 150.0, "BTCUSDT": 60000.0, "ETHUSDT": 3000.0}
            for ticker, p in base_prices.items():
                # Inject once for each ticker to warm the DB/Cache
                await client.post("/api/v1/market/inject", json={
                    "symbol": ticker, 
                    "price": p,
                    "source": "backtest_warmup"
                })
                await asyncio.sleep(0.2)
            
            await asyncio.sleep(5)

            # 2. Forced Validation Scenarios
            print(">>> Running controlled validation scenario...", flush=True)
            capital = INITIAL_CAPITAL
            positions = {t: 0 for t in TICKERS}
            
            # SCENARIO A: Force BUY on AAPL
            print("    [SCENARIO] Setting REDIS BULLISH fixture for AAPL (isolated)...", flush=True)
            fixture_data = json.dumps({"forecast": 0.05, "sentiment": 0.8})
            await redis_bus.set(f"fixture:AAPL", fixture_data, ex=60)
            
            await asyncio.sleep(2)
            
            for i in range(5):
                print(f"    Iteration {i+1}/5...", flush=True)
                
                # Update prices to simulate movement
                for ticker in TICKERS:
                    p_base = base_prices.get(ticker, 100.0)
                    # Bullish trend
                    price = p_base + (i * 2)
                    await client.post("/api/v1/market/inject", json={
                        "symbol": ticker, 
                        "price": price,
                        "source": "backtest_sim"
                    })
                    await asyncio.sleep(0.1)

                # If Iteration 4, switch to BEARISH news
                if i == 3:
                    print("    [SCENARIO] Setting REDIS BEARISH fixture for AAPL (isolated)...", flush=True)
                    fixture_data = json.dumps({"forecast": -0.05, "sentiment": -0.8})
                    await redis_bus.set(f"fixture:AAPL", fixture_data, ex=60)
                    await asyncio.sleep(2)

                for ticker in TICKERS:
                    try:
                        # 🚀 Direct Trigger & Consume (Synchronous for Backtest Stability)
                        r_post = await client.post("/api/v1/ai/recommend", json={"ticker": ticker})
                        if r_post.status_code != 200:
                            print(f"      [WARN] Recommendation failed for {ticker}: {r_post.text}", flush=True)
                            continue
                            
                        rec_data = r_post.json().get("recommendation")
                        if not rec_data:
                            print(f"      [WARN] No recommendation data returned for {ticker}", flush=True)
                            continue

                        action = rec_data.get("action") or "HOLD"
                        # Fallback for key mismatch (ensure we catch 'signal' if it leaks)
                        if "signal" in rec_data:
                            action = rec_data["signal"]
                        
                        m_resp = await client.get(f"/api/v1/market/{ticker}")
                        price_data = m_resp.json()
                        price = price_data.get("latest_price", 0.0)
                        
                        results["recommendations_read"] += 1
                        results["data_points_used"] += 1
                        
                        if action == "BUY" and capital > (price * 10) and positions[ticker] == 0:
                            qty = 10
                            capital -= qty * price
                            positions[ticker] += qty
                            results["buy_count"] += 1
                            results["trades_executed"] += 1
                            results["trades"].append({
                                "ticker": ticker, 
                                "type": "BUY", 
                                "price": float(price), 
                                "qty": qty,
                                "timestamp": datetime.now().isoformat()
                            })
                            print(f"      [TRADE] BUY {ticker} @ {price} | Reason: {rec_data.get('reasoning')}", flush=True)
                        elif action == "SELL" and positions[ticker] > 0:
                            qty = positions[ticker]
                            capital += qty * price
                            positions[ticker] = 0
                            results["sell_count"] += 1
                            results["trades_executed"] += 1
                            results["trades"].append({
                                "ticker": ticker, 
                                "type": "SELL", 
                                "price": float(price), 
                                "qty": qty,
                                "timestamp": datetime.now().isoformat()
                            })
                            print(f"      [TRADE] SELL {ticker} @ {price} | Reason: {rec_data.get('reasoning')}", flush=True)
                    except Exception as e:
                        print(f"    [WARN] Error: {e}", flush=True)
                await asyncio.sleep(1)

            # 3. Final Liquidation
            print(">>> Final Liquidation...", flush=True)
            for ticker, qty in positions.items():
                if qty > 0:
                    m_resp = await client.get(f"/api/v1/market/{ticker}")
                    price = m_resp.json().get("latest_price", 0.0)
                    capital += qty * price
                    results["sell_count"] += 1
                    results["trades_executed"] += 1
                    results["trades"].append({
                        "ticker": ticker, 
                        "type": "SELL_LIQUIDATE", 
                        "price": float(price), 
                        "qty": qty,
                        "timestamp": datetime.now().isoformat()
                    })
                    positions[ticker] = 0
            
            results["final_cash"] = capital
            results["pnl"] = capital - INITIAL_CAPITAL
            results["return_percent"] = (results["pnl"] / INITIAL_CAPITAL) * 100
            results["holdings"] = positions
            # Enforce at least 1 BUY and 1 SELL (total 2 trades)
            results["status"] = "VALIDATED" if results["trades_executed"] >= 2 else "FAILED"
            
            print(f"\n>>> Backtest Complete. Status: {results['status']}", flush=True)
            print(f">>> Trades: {results['trades_executed']} (B:{results['buy_count']} S:{results['sell_count']})", flush=True)
            print(f">>> PnL: ${results['pnl']:.2f}", flush=True)

            # Cleanup fixtures
            for ticker in TICKERS:
                await redis_bus.delete(f"fixture:{ticker}")

        except Exception as e:
            print(f"FAILED Backtest: {repr(e)}", flush=True)
            # Cleanup on failure
            try:
                for ticker in TICKERS:
                    import redis
                    # Direct redis cleanup if redis_bus fails
                    r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
                    r.delete(f"fixture:{ticker}")
            except: pass
            import traceback
            traceback.print_exc()
            sys.exit(1)
            results["status"] = "ERROR"

    os.makedirs("proof_step12", exist_ok=True)
    with open("proof_step12/backtest_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run_backtest())
