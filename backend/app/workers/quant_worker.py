"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Runs quantitative signal generation for forecast and recommendation support.
"""
from __future__ import annotations
import asyncio, time
from loguru import logger
import json
import uuid
from datetime import datetime, timezone
from collections import deque
from typing import cast, List, Dict, Any, Optional
import sys
import os
import numpy as np

# Ensure the project root is in the python path for IDE resolution
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.redis_client import redis_bus
from app.models.schemas.domain_schemas import TickData, NewsEvent, AISignal
from app.services.ai_engine.xgboost_inference import xgboost_engine

# Managed by main.py

class OracleMatrix:
    """
    The Core Decision Engine for the AI Portfolio.
    Fuses Technical Indicators (RSI, MACD) with live NLP Sentiment.
    """
    def __init__(self):
        # We need to maintain a rolling window of prices per asset to calculate indicators
        self.price_history: Dict[str, deque] = {
            "BTC/USD": deque(maxlen=200),
            "XAU/USD": deque(maxlen=200),
            "EUR/USD": deque(maxlen=200),
            "USD/TRY": deque(maxlen=200),
            "GBP/USD": deque(maxlen=200),
            "CL=F": deque(maxlen=200) # Oil
        }
        
        # Keep track of the most recent global sentiment and macro triggers
        self.latest_global_sentiment = 0.0
        self.recent_macro_context = {"energy": False, "metals": False, "logistics": False}
        self.recent_macro_context = {"energy": False, "metals": False, "logistics": False}
        # AI Model Integration (Hardened XGBoost Inference)
        self.predictor = xgboost_engine
        
        # 🔹 MACRO INTELLIGENCE LAYER
        self.macro_keywords = [
            "Fed", "Interest Rate", "Inflation", "OPEC", "CPI", 
            "Oil", "Gold", "Macro", "Treasury", "Yield", "GDP"
        ]

        # 🔹 DYNAMIC REASONING ENGINE (White-Box AI)
        self.reason_templates = {
            "RSI_OVERSOLD": "[STRAT-RSI] Oversold ({rsi:.1f}) | Mean Reversion Vector Detected",
            "RSI_OVERBOUGHT": "[STRAT-RSI] Overbought ({rsi:.1f}) | Exhaustion Level Identified",
            "GOLDEN_CROSS": "[TECH-EMA] Golden Cross ({short}/{long}) | Bullish Trend Acceleration",
            "DEATH_CROSS": "[TECH-EMA] Death Cross ({short}/{long}) | Bearish Structural Breakdown",
            "MACD_BULLISH": "[ALPHA-MACD] Crossover ({macd:.4f}) | Positive Momentum Divergence",
            "MACD_BEARISH": "[ALPHA-MACD] Neg. Hst. ({macd:.4f}) | Downward Impulse Confirmed",
            "SENT_CATALYST": "[NLP-SENT] Catalyst (Score: {sent:.2f}) | Institutional Inflow Detected",
            "SENT_RISK": "[NLP-SENT] Risk Event (Score: {sent:.2f}) | Systemic Sentiment Drain",
            "VOL_EXPANSION": "[TECH-VOL] Regime Shift | High-Gamma Volatility Expansion Detected",
            "CORREL_SYNC": "[MULTI-COR] Asset Sync | Cross-Domain Corridor Convergence",
            "MEAN_REV": "[STRAT-REV] Variance Breach | Statistical Mean Reversion Predicted",
            "MOM_BREAK": "[ALPHA-MOM] Velocity Cap | Bullish Momentum Exhaustion identified"
        }


    def _calculate_rsi(self, prices: List[float], periods: int = 14) -> float:
        if len(prices) < periods + 1:
            return 50.0 # Default Neutral
        
        deltas = np.diff(prices)
        seed = deltas[:periods]
        up = seed[seed >= 0].sum() / periods
        down = -seed[seed < 0].sum() / periods
        if down == 0: return 100.0
        
        rs = up / down
        rsi = np.zeros_like(prices)
        rsi[:periods] = 100. - 100. / (1. + rs)

        for i in range(periods, len(prices)):
            delta = deltas[i - 1] 
            if delta > 0:
                upval = delta
                downval = 0.
            else:
                upval = 0.
                downval = -delta

            up = (up * (periods - 1) + upval) / periods
            down = (down * (periods - 1) + downval) / periods
            rs = up / down
            rsi[i] = 100. - 100. / (1. + rs)
            
        return float(rsi[-1])

    def _calculate_sma(self, prices: List[float], window: int) -> float:
        if len(prices) < window: return prices[-1] if prices else 0.0
        return float(np.mean(np.array(prices[-window:])))

    def _calculate_macd(self, prices: List[float]) -> Dict[str, float]:
        """Calculates MACD (12, 26, 9) for real-time trend confirmation."""
        import pandas as pd
        if len(prices) < 26:
            return {"macd": 0.0, "signal": 0.0, "hist": 0.0}
        
        ema12 = pd.Series(prices).ewm(span=12, adjust=False).mean()
        ema26 = pd.Series(prices).ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            "macd": float(macd_line.iloc[-1]),
            "signal": float(signal_line.iloc[-1]),
            "hist": float(histogram.iloc[-1])
        }


    async def evaluate_tick(self, tick: TickData) -> Optional[AISignal]:
        """
        The Master Rule Engine: Evaluates a single tick against the Matrix.
        Returns an AISignal if an actionable threshold is breached, else None.
        """
        if tick.ticker not in self.price_history:
            self.price_history[tick.ticker] = deque(maxlen=200)
            
        history = self.price_history[tick.ticker]
        history.append(tick.price)
        prices = cast(List[float], list(history))

        # Need minimum data to make intelligent decisions
        if len(prices) < 3:
            return None 

        # 1. Compute Technicals
        current_price = tick.price
        rsi = self._calculate_rsi(prices, periods=14)
        sma_short = self._calculate_sma(prices, 9)
        sma_long = self._calculate_sma(prices, 20)
        macd = self._calculate_macd(prices)
        
        # Momentum (Rate of change over last 5 ticks)
        momentum = (current_price - prices[-5]) / prices[-5] if len(prices) >= 5 else 0

        # 2. Integrate NLP Sentiment
        sentiment = self.latest_global_sentiment
        
        # 3. Decision Logic Matrix
        action = "WAIT"
        bull_reasons = []
        bear_reasons = []

        # --- BULLISH RULES ---
        score = 0
        if rsi < 30:
            score += 3
            bull_reasons.append(self.reason_templates["RSI_OVERSOLD"].format(rsi=rsi))
        if sma_short > sma_long:
            score += 2
            bull_reasons.append(self.reason_templates["GOLDEN_CROSS"].format(short=9, long=20))
        if macd["hist"] > 0 and macd["macd"] > macd["signal"]:
            score += 2
            bull_reasons.append(self.reason_templates["MACD_BULLISH"].format(macd=macd["hist"]))
        if sentiment > 0.3:
            score += 3
            bull_reasons.append(self.reason_templates["SENT_CATALYST"].format(sent=sentiment))

        # --- BEARISH RULES ---
        bear_score = 0
        if rsi > 70:
            bear_score += 3
            bear_reasons.append(self.reason_templates["RSI_OVERBOUGHT"].format(rsi=rsi))
        if sma_short < sma_long:
            bear_score += 2
            bear_reasons.append(self.reason_templates["DEATH_CROSS"].format(short=9, long=20))
        if macd["hist"] < 0:
            bear_score += 2
            bear_reasons.append(self.reason_templates["MACD_BEARISH"].format(macd=macd["hist"]))
        if sentiment < -0.3:
            bear_score += 3
            bear_reasons.append(self.reason_templates["SENT_CATALYST"].format(sent=sentiment))

        # 🔹 CROSS-SECTOR CORRELATION (Requirement #4: Macro Impact)
        # Check global macro impact on the specific ticker
        macro_multi = 1.0
        if tick.asset_type in ["commodity", "forex"]:
            # Check for explicit sector hits from the NLP Macro Layer
            impact = self.recent_macro_context
            hit = False
            if tick.ticker in ["XAU/USD"] and impact.get("metals"):
                macro_multi = 1.4
                hit = True
            elif tick.ticker in ["CL=F"] and impact.get("energy"):
                macro_multi = 1.4
                hit = True
            elif impact.get("logistics"): # Global Logistics impacts all tradeable risk
                macro_multi = 1.2
                hit = True
                
            if hit:
                bear_reasons.append(f"Macro-Convergence: {tick.ticker} correlated with Global Events ({macro_multi}x)")
                if score > 0: score = int(score * macro_multi)
                if bear_score > 0: bear_score = int(bear_score * macro_multi)
        
        final_score = score - bear_score
        
        # 🔹 Log reconciliation for debugging (Requirement #7: Unified Traceability)
        logger.debug(f"📊 [MATRIX] {tick.ticker} | Score: {final_score} | Sentiment: {sentiment:.2f} | Macro: {macro_multi}x")
        
        # Convert prices to a numpy array to prevent internal caught AttributeErrors in np.mean/np.std
        # that trigger the VS Code debugger when 'Raised Exceptions' is enabled.
        prices_arr = np.array(prices)
        volatility = np.std(prices_arr) / np.mean(prices_arr) if len(prices_arr) > 2 else 0.001
        
        # 🔹 USE HARDENED INFERENCE ENGINE
        xgb_res = await self.predictor.predict(tick.ticker)
        
        if xgb_res.get("status") == "success":
            ml_pred = xgb_res["prediction"]
            ml_conf = xgb_res["confidence"]
            # Map "Bullish" -> 1, "Bearish" -> 0, "Neutral" -> 0.5 (as a proxy for binary direction)
            ml_dir = 1 if ml_pred == "Bullish" else 0
        else:
            ml_dir = 0
            ml_conf = 0.0
            logger.warning(f"ML Inference unavailable for {tick.ticker}: {xgb_res.get('reason')}")
        
        # 🔹 INSTITUTIONAL CONFLUENCE MATRIX (Mathematical Truth)
        # Weights: 40% Tech | 30% Sent | 30% ML
        tech_score = min(1.0, max(0.0, (final_score + 10) / 20.0))
        
        # ML signal alignment: if ML says Bullish and Tech says Bullish, they align.
        ml_aligned = (ml_dir == 1 and final_score >= 0) or (ml_dir == 0 and final_score < 0)
        ml_score = ml_conf if ml_aligned else (1 - ml_conf) if ml_conf > 0 else 0.5
        
        calculated_conf = (0.4 * tech_score) + (0.3 * abs(sentiment)) + (0.3 * ml_score)
        process_ts = time.time()

        # 🔹 PRODUCTION THRESHOLDS
        # Technical-only mode (no news):  0.55+ Strong | 0.22+ Active | <0.22 Watch
        # Full fusion mode (with news):   0.60+ Strong | 0.30+ Active | <0.30 Watch
        strong_thresh = 0.55 if abs(sentiment) < 0.01 else 0.60
        active_thresh = 0.22 if abs(sentiment) < 0.01 else 0.30

        if calculated_conf >= strong_thresh:
            action = "STRONG_BUY" if final_score >= 0 else "STRONG_SELL"
        elif calculated_conf >= active_thresh:
            action = "BUY" if final_score >= 0 else "SELL"
        else:
            action = "WATCH"

        # 🔹 DYNAMIC REASONING ENGINE (Requirement #4) - Contextual Logic
        primary_reason = "Market Equilibrium"
        if final_score > 0 and bull_reasons:
            primary_reason = bull_reasons[0]
        elif final_score < 0 and bear_reasons:
            primary_reason = bear_reasons[0]
        
        indicators = f"Tech: {tech_score:.2f} | Sent: {sentiment:.2f} | ML: {ml_conf:.2f}"
        reasoning = f"{primary_reason} | Matrix: {indicators}"
        if action == "WATCH":
            reasoning = f"Monitoring {tick.ticker}. Confluence {calculated_conf:.2f} | Building price history..."

        return AISignal(
            ticker=tick.ticker,
            action=action, # type: ignore
            confidence=float(f"{calculated_conf:.4f}"), 
            reasoning=reasoning,
            ingest_ts=tick.ingest_ts,
            process_ts=process_ts,
            signal_ts=datetime.now(timezone.utc).timestamp()
        )


class QuantWorker:
    def __init__(self):
        self.oracle: Optional[OracleMatrix] = None
        self.last_signal_time: Dict[str, float] = {} 

    async def run(self):
        # 🛡️ LAZY INITIALIZATION: Prevent heavy ML training during module import
        if not self.oracle:
            self.oracle = OracleMatrix()
            
        await redis_bus.connect()
        logger.info("Quant Worker [The Oracle] Online. Subscribing to Event Bus...")
        
        # We need to listen to both price updates AND news simultaneously.
        # So we create background tasks.
        asyncio.create_task(self._listen_to_news())
        asyncio.create_task(self._sentiment_heartbeat())
        await self._listen_to_markets()

    async def _sentiment_heartbeat(self):
        """Periodically broadcasts the global sentiment aggregate to the UI."""
        while True:
            try:
                if not self.oracle:
                    await asyncio.sleep(2)
                    continue
                # 🔹 Real-time sentiment monitor (Raw NLP Output)
                sent = self.oracle.latest_global_sentiment
                await redis_bus.publish("ai_sentiment_aggregate", {
                    "score": round(sent, 3),
                    "label": "Bullish" if sent > 0.05 else "Bearish" if sent < -0.05 else "Neutral",
                    "timestamp": datetime.now().isoformat()
                })
                # High frequency heartbeat for the defense
                # logger.info(f"💓 [HEARTBEAT] Global Sentiment: {sent:.2f}")
            except Exception as e:
                logger.error(f"Sentiment Heartbeat Error: {e}")
            await asyncio.sleep(2) # Faster updates

    async def _listen_to_news(self):
        """Maintains the Oracle's awareness of global NLP sentiment."""
        async for msg in redis_bus.subscribe("news_scored"):
            try:
                # 🔹 Agnostic Parsing: Handle both JSON string (Redis) and dict (Local Fallback)
                if isinstance(msg, dict):
                    news = NewsEvent.model_validate(msg)
                else:
                    news = NewsEvent.model_validate_json(msg)
                    
                if news.sentiment_score is not None and self.oracle:
                    # 🔹 High Sensitivity EMA: Responds faster to news for the verification
                    prev = self.oracle.latest_global_sentiment
                    self.oracle.latest_global_sentiment = (0.4 * prev) + (0.6 * news.sentiment_score)
                    
                    # 🔹 Advisory Sync: Pass Macro-Impact to the Oracle Matrix
                    raw = msg if isinstance(msg, dict) else json.loads(msg)
                    self.oracle.recent_macro_context = raw.get("macro_impact", {})
                        
                    logger.info(f"🗞️ [NEWS SWEEP] Aggregate Sentiment: {self.oracle.latest_global_sentiment:.3f} | Macro: {self.oracle.recent_macro_context}")
            except Exception as e:
                logger.error(f"Failed to parse scored news: {e}")

    async def _listen_to_markets(self):
        """The main high-frequency loop processing every tick."""
        async for msg in redis_bus.subscribe("market_ticks"):
            try:
                # 🔹 Agnostic Parsing: Essential for verification Mode stability
                if isinstance(msg, dict):
                    tick = TickData.model_validate(msg)
                else:
                    tick = TickData.model_validate_json(msg)
                
                # 1. Ask the Oracle for a decision on this tick
                if self.oracle:
                    signal = await self.oracle.evaluate_tick(tick)
                else:
                    signal = None
                
                if signal:
                    now = datetime.now(timezone.utc).timestamp()
                    last_ts = self.last_signal_time.get(tick.ticker, 0.0)
                    
                    # 2. Throttle signals (e.g., max 1 signal per minute per asset)
                    if (now - last_ts) > 2:
                        self.last_signal_time[tick.ticker] = now
                        
                        logger.info(f"🔮 [ORACLE] {signal.ticker} -> {signal.action} ({signal.confidence*100}%) | {signal.reasoning}")
                        
                        # 3. Publish the final decision back to Redis 
                        # so the Dashboard UI and Execution Engine see it instantly
                        await redis_bus.publish("ai_signals", signal.model_dump(mode="json"))

            except Exception as e:
                logger.error(f"Quant Worker error: {e}")

if __name__ == "__main__":
    worker = QuantWorker()
    asyncio.run(worker.run())

# Singleton for API access
quant_worker = QuantWorker()
