"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Combines prediction, sentiment, event, and price signals into BUY/SELL/HOLD advice.
- Persists recommendation evidence for dashboard display and audit review.
"""

import os
from typing import Optional, Dict, Any
from datetime import datetime
import time
from loguru import logger
from app.core.redis_client import redis_bus
from app.core.config import settings
from sqlalchemy import select, desc
from app.core.db import AsyncSessionLocal
from app.models.all_models import Prediction, Sentiment, Event, Recommendation, Asset, PriceHistory

class RecommenderService:
    """
    Synthesize AI signals into explainable BUY/SELL/HOLD recommendations.

    The service gathers the latest forecast, sentiment, event, and price context,
    then persists a recommendation so the dashboard and audit log inspect the
    same decision record.
    """

    async def get_latest_signals(self, asset_id: int) -> Dict[str, Any]:
        """
        Fetch latest prediction, sentiment, event, and price evidence for an asset.

        Rows are selected deterministically by most recent timestamps and returned
        as plain values to avoid ORM session-detachment issues in the scoring path.
        """
        async with AsyncSessionLocal() as session:
            # 1. Latest Prediction
            pred_query = (
                select(Prediction.target_price, Prediction.timestamp, Prediction.process_ts, Prediction.ingest_ts)
                .where(Prediction.asset_id == asset_id)
                .order_by(desc(Prediction.timestamp))
                .limit(1)
            )
            prediction_row = (await session.execute(pred_query)).first()

            # 2. Latest Sentiment
            sent_query = (
                select(Sentiment.score, Sentiment.label)
                .where(Sentiment.asset_id == asset_id)
                .order_by(desc(Sentiment.created_at))
                .limit(1)
            )
            sentiment_row = (await session.execute(sent_query)).first()

            # 3. Latest Event (Asset-specific or Macro)
            event_query = (
                select(Event.event_type, Event.magnitude)
                .where((Event.asset_id == asset_id) | (Event.asset_id == None))
                .order_by(desc(Event.timestamp))
                .limit(1)
            )
            event_row = (await session.execute(event_query)).first()

            # 4. Latest Price (Cache-First for Step 11/12 responsiveness)
            from app.services.cache_service import performance_cache
            
            asset_obj = await session.get(Asset, asset_id)
            ticker = asset_obj.ticker if asset_obj else None
            
            price_val = None
            ingest_ts = None
            
            if ticker:
                # Validation fixtures let tests exercise deterministic BUY/SELL
                # paths without pretending the fixture is live market/news data.
                if settings.STEP12_VALIDATION_MODE:
                    fixture_key = f"fixture:{ticker.upper()}"
                    fixture_raw = await redis_bus.get(fixture_key)
                    if fixture_raw:
                        import json
                        fix = json.loads(fixture_raw)
                        # We still need the current price for delta calculation
                        price_cached = await performance_cache.get(f"latest:tick:{ticker.upper()}")
                        p_val = price_cached.get("price") if price_cached else None
                        p_ingest = price_cached.get("ingest_ts") if price_cached else None
                        
                        if p_val is None:
                            # Try DB fallback even in validation mode
                            price_query = (
                                select(PriceHistory.price, PriceHistory.ingest_ts)
                                .where(PriceHistory.asset_id == asset_id)
                                .order_by(desc(PriceHistory.timestamp))
                                .limit(1)
                            )
                            p_row = (await session.execute(price_query)).first()
                            if p_row:
                                p_val, p_ingest = p_row
                        
                        if p_val is None:
                            logger.error(f"Cannot generate validation fixture for {ticker}: No price data found.")
                            return None

                        return {
                            "prediction": {"target_price": p_val * (1 + fix["forecast"]), "timestamp": time.time(), "source": "validation_fixture"},
                            "sentiment": {
                                "score": fix["sentiment"], 
                                "label": "BULLISH_FIXTURE" if fix["sentiment"] > 0 else "BEARISH_FIXTURE",
                                "source": "validation_fixture"
                            },
                            "event": None,
                            "current_price": p_val,
                            "ingest_ts": p_ingest or time.time(),
                            "data_source": "validation_mode"
                        }

                cached = await performance_cache.get(f"latest:tick:{ticker.upper()}")
                if cached:
                    price_val = cached.get("price")
                    ingest_ts = cached.get("ingest_ts")
            
            if price_val is None:
                price_query = (
                    select(PriceHistory.price, PriceHistory.ingest_ts)
                    .where(PriceHistory.asset_id == asset_id)
                    .order_by(desc(PriceHistory.timestamp))
                    .limit(1)
                )
                p_row = (await session.execute(price_query)).first()
                if p_row:
                    price_val, ingest_ts = p_row
            
            return {
                "prediction": {
                    "target_price": prediction_row[0], 
                    "timestamp": prediction_row[1], 
                    "process_ts": prediction_row[2] if len(prediction_row) > 2 else None,
                    "ingest_ts": prediction_row[3] if len(prediction_row) > 3 else None,
                    "source": "database_ml"
                } if prediction_row else None,
                "sentiment": {"score": sentiment_row[0], "label": sentiment_row[1], "source": "database_nlp"} if sentiment_row else None,
                "event": {"event_type": event_row[0], "magnitude": event_row[1], "source": "database_event"} if event_row else None,
                "current_price": price_val,
                "ingest_ts": ingest_ts,
                "data_source": "production_live"
            }

    def _calculate_confidence(self, forecast_delta_pct: float, sentiment_score: float, event_mod: float) -> float:
        """
        Calculate bounded recommendation confidence from signal strength.

        Inputs are forecast delta, sentiment score, and event magnitude. The
        output is a 0..1 score used by the dashboard to show conviction without
        claiming certainty.
        """
        # Normalize a 10 percent forecast move to roughly half the confidence range.
        f_conf = min(abs(forecast_delta_pct) * 5.0, 0.5)
        # Sentiment scores are bounded near -1..1 by the NLP service.
        s_conf = abs(sentiment_score) * 0.3
        # Event magnitude provides a smaller modifier than price/sentiment evidence.
        e_conf = min(abs(event_mod) * 0.2, 0.2)
        
        return min(max(f_conf + s_conf + e_conf, 0.0), 1.0)

    async def generate_recommendation(self, asset_id: int, portfolio_id: Optional[int] = None, trigger_source: str = "manual", ingest_ts: Optional[float] = None, process_ts: Optional[float] = None, ml_signal: Optional[Dict] = None) -> Optional[dict]:
        """
        Generate and persist one explainable recommendation.

        Logic:
        - Forecast Up + Positive Sentiment -> BUY
        - Forecast Down + Negative Sentiment -> SELL
        - Mixed/Weak -> HOLD
        
        Event Influence:
        - Normalizes event types (case-insensitive).
        - Applies bias to decision score and confidence.
        """
        signals = await self.get_latest_signals(asset_id)
        if not signals:
            logger.warning(f"No signals found for asset_id {asset_id}. Defaulting to HOLD.")
            return await self._persist_recommendation(
                asset_id, "HOLD", 0.0, "Insufficient real signals; no data available in database.", 
                portfolio_id, trigger_source,
                time.time(), time.time(), time.time(), None,
                data_source="unavailable"
            )
            
        prediction = signals.get("prediction")
        sentiment = signals.get("sentiment")
        event = signals.get("event")
        current_price = signals.get("current_price")
        
        # Load model validation metrics so reasoning can disclose when XGBoost
        # is used only as a weak signal rather than a standalone decision engine.
        honest_warning = ""
        try:
            metrics_path = os.path.join(os.getcwd(), "data/training/artifacts/xgboost_metrics.json")
            if os.path.exists(metrics_path):
                with open(metrics_path, "r") as f:
                    import json
                    metrics = json.load(f)
                    baseline_pass = metrics.get("baseline_pass", False)
                    beats_majority = True
                    if isinstance(baseline_pass, dict):
                        beats_majority = baseline_pass.get("xgboost_beats_majority", True)
                    else:
                        beats_majority = bool(baseline_pass)

                    if not beats_majority:
                        honest_warning = "XGBoost did not outperform the majority baseline; it is used as one weak signal inside a multi-signal recommendation engine."
        except Exception as e:
            logger.warning(f"Could not load honest metrics for reasoning: {e}")

        # Fetch the ticker in a short-lived session for logs and response payloads.
        ticker = "UNKNOWN"
        async with AsyncSessionLocal() as session:
            asset_stmt = select(Asset).where(Asset.id == asset_id)
            asset_res = await session.execute(asset_stmt)
            asset_obj = asset_res.scalar_one_or_none()
            if asset_obj:
                ticker = asset_obj.ticker

        # Resolve latency markers before scoring so the persisted recommendation
        # can be traced from ingestion through signal generation.
        ingest_ts = ingest_ts or (prediction.get("ingest_ts") if prediction else None) or time.time()
        process_ts = process_ts or (prediction.get("process_ts") if prediction else None) or time.time()
        signal_ts = time.time()

        # Missing forecast or price data produces HOLD with explicit reasoning
        # rather than inventing a recommendation.
        if (not prediction and not ml_signal) or current_price is None:
            logger.warning(f"Missing core signals (forecast/price) for asset_id {asset_id}. Defaulting to HOLD.")
            reason = "Missing core signals (forecast/price)." if (not prediction and not ml_signal) else "Execution price unavailable."
            return await self._persist_recommendation(
                asset_id, "HOLD", 0.0, f"Insufficient real signals: {reason}", 
                portfolio_id, trigger_source,
                ingest_ts, process_ts, signal_ts, current_price,
                data_source="unavailable",
                sentiment_label="WAITING", sentiment_score=0.5, prediction_label="ANALYZING"
            )

        # Convert model output or stored forecast into a comparable forecast delta.
        forecast_delta = 0.0
        ml_prediction = None
        if ml_signal and ml_signal.get("status") == "success":
            ml_prediction = ml_signal.get("prediction")
            forecast_delta = 0.05 if ml_prediction == "Bullish" else (-0.05 if ml_prediction == "Bearish" else 0.0)
            logger.info(f"Using Validated Binary ML Signal: {ml_prediction}")
        elif prediction:
            forecast_price = prediction["target_price"]
            forecast_delta = (forecast_price - current_price) / current_price
            
        sentiment_score = sentiment["score"] if sentiment else 0.0
        
        # Normalize event type and apply a small rule-based decision bias.
        event_type = event["event_type"].upper() if event else "NONE"
        event_magnitude = event["magnitude"] if event else 0.0
        
        # event_bias influences the final decision score without overriding
        # missing data or confidence bounds.
        event_bias = 0.0
        if "EARNINGS" in event_type:
            # Earnings usually amplifies current sentiment/forecast
            event_bias = 0.1 * (1 if sentiment_score > 0 else -1)
        elif "REGULATORY" in event_type or "LAWSUIT" in event_type:
            # Regulatory events usually create negative pressure
            event_bias = -0.15
        elif "MACRO" in event_type:
            # Macro bias (e.g. Fed hawkish/dovish)
            event_bias = 0.05 * (1 if sentiment_score > 0 else -1)
        elif "MERGER" in event_type:
            # Merger/Acquisition usually positive bias
            event_bias = 0.2

        # Multi-signal decision score combines forecast, sentiment, and event
        # context. XGBoost remains one input to this explainable rule layer.
        decision_score = (forecast_delta * 10) * 0.7 + sentiment_score * 0.3 + event_bias
        logger.debug(f"[RECOMMENDER] {ticker} | Score: {decision_score:.4f} | Forecast: {forecast_delta:.4f} | Sentiment: {sentiment_score:.4f}")
        
        signal = "HOLD"
        reasoning_parts = []

        # Validation fixtures intentionally force BUY/SELL to prove both paths
        # without changing normal production recommendation behavior.
        if settings.STEP12_VALIDATION_MODE and sentiment:
            label = sentiment.get("label", "").upper()
            if "FIXTURE" in label:
                if "BULLISH" in label:
                    signal = "BUY"
                    reasoning_parts.append("Validation Override: BULLISH Fixture Detected")
                    logger.info(f"[VALIDATION] Triggered BULLISH override for {ticker}")
                elif "BEARISH" in label:
                    signal = "SELL"
                    reasoning_parts.append("Validation Override: BEARISH Fixture Detected")
                    logger.info(f"[VALIDATION] Triggered BEARISH override for {ticker}")

        if signal == "HOLD":
            if decision_score > 0.15:
                signal = "BUY"
                reasoning_parts.append(f"Bullish Score ({decision_score:.2f})")
            elif decision_score < -0.15:
                signal = "SELL"
                reasoning_parts.append(f"Bearish Score ({decision_score:.2f})")
            else:
                signal = "HOLD"
                reasoning_parts.append(f"Neutral Score ({decision_score:.2f})")

        # Reasoning text is persisted so the dashboard and audit log explain the
        # same decision the service actually stored.
        if ml_prediction:
            reasoning_parts.append(f"Validated ML: {ml_prediction}")
        else:
            reasoning_parts.append(f"Forecast: {forecast_delta:+.2%}")
        reasoning_parts.append(f"Sentiment: {sentiment_score:.2f}")
        if event:
            reasoning_parts.append(f"Event: {event['event_type']} (Bias: {event_bias:+.2f})")

        # Confidence starts from signal strength and receives a small boost when
        # event direction agrees with the final action.
        base_confidence = self._calculate_confidence(forecast_delta, sentiment_score, event_magnitude)
        if (signal == "BUY" and event_bias > 0) or (signal == "SELL" and event_bias < 0):
            confidence = min(base_confidence + 0.1, 1.0)
        else:
            confidence = base_confidence

        # Persist before publishing so downstream UI state points to a DB-backed
        # recommendation rather than a transient calculation only.
        reasoning = " | ".join(reasoning_parts)
        if honest_warning:
            reasoning = f"{honest_warning} | {reasoning}"
            
        # Dashboard metadata mirrors the persisted reasoning and labels.
        s_label = sentiment.get("label", "NEUTRAL") if sentiment else "NEUTRAL"
        s_score = sentiment.get("score", 0.5) if sentiment else 0.5
        
        # Map forecast direction into the compact label used by the AI board.
        p_label = "STABLE"
        if ml_prediction:
            p_label = "UP" if ml_prediction == "Bullish" else "DOWN" if ml_prediction == "Bearish" else "STABLE"
        else:
            if forecast_delta > 0.01: p_label = "UP"
            elif forecast_delta < -0.01: p_label = "DOWN"

        return await self._persist_recommendation(
            asset_id, signal, confidence, reasoning, portfolio_id, 
            trigger_source, ingest_ts, process_ts, signal_ts, current_price,
            data_source=signals.get("data_source", "unknown"),
            sentiment_label=s_label, sentiment_score=s_score, prediction_label=p_label
        )

    async def _persist_recommendation(self, asset_id: int, signal: str, confidence: float, reasoning: str, 
                                     portfolio_id: Optional[int], trigger_source: str, 
                                     ingest_ts: float, process_ts: float, signal_ts: float, current_price: float,
                                     data_source: str = "unknown",
                                     sentiment_label: str = "NEUTRAL",
                                     sentiment_score: float = 0.5,
                                     prediction_label: str = "STABLE") -> dict:
        """
        Persist one recommendation and publish it to Redis streams.

        Inputs are the chosen action, confidence, reasoning, latency markers,
        and dashboard labels. The returned dict is the API/WebSocket shape used
        by the frontend and validation scripts.
        """
        async with AsyncSessionLocal() as session:
            # Fetch Asset first so Redis messages use the human-readable ticker.
            asset_obj = await session.get(Asset, asset_id)
            ticker = asset_obj.ticker if asset_obj else str(asset_id)

            rec = Recommendation(
                asset_id=asset_id,
                portfolio_id=portfolio_id,
                signal=signal,
                confidence=confidence,
                reasoning=reasoning,
                ingest_ts=ingest_ts,
                process_ts=process_ts,
                signal_ts=signal_ts,
                execution_price=current_price,
                sentiment_label=sentiment_label,
                sentiment_score=sentiment_score,
                prediction_label=prediction_label
            )
            session.add(rec)
            await session.commit()
            
            # Redis publish keeps live dashboard views synchronized with the
            # database-backed recommendation.
            try:
                from app.core.redis_client import redis_bus
                
                payload = {
                    "asset_id": asset_id,
                    "ticker": ticker,
                    "action": signal,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "timestamp": datetime.now().timestamp(), # Float timestamp for E2E delay calculation.
                    "trigger_source": trigger_source,
                    "ingest_ts": ingest_ts,
                    "process_ts": process_ts,
                    "signal_ts": signal_ts,
                    "execution_price": current_price,
                    "data_source": data_source,
                    "sentiment_label": sentiment_label,
                    "sentiment_score": sentiment_score,
                    "prediction_label": prediction_label
                }
                await redis_bus.publish("ai_signals", payload)
                await redis_bus.publish("recommendations", payload) # UI stream compatibility.
            except Exception as e:
                logger.error(f"Failed to publish recommendation to Redis: {e}")

            logger.info(f"Recommendation Generated | Asset: {ticker} ({asset_id}) | Action: {signal} | Conf: {confidence:.2f} | Reason: {reasoning}")
            
            return {
                "asset_id": asset_id,
                "ticker": ticker,
                "portfolio_id": portfolio_id,
                "action": signal,
                "confidence": confidence,
                "reasoning": reasoning,
                "timestamp": signal_ts,
                "ingest_ts": ingest_ts,
                "process_ts": process_ts,
                "signal_ts": signal_ts,
                "execution_price": current_price,
                "trigger_source": trigger_source,
                "data_source": data_source,
                "sentiment_label": sentiment_label,
                "sentiment_score": sentiment_score,
                "prediction_label": prediction_label
            }

# Shared service instance used by API routes and background workers.
recommender_service = RecommenderService()
