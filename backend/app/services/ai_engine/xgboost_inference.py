"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Loads XGBoost artifacts and produces truth-aware model predictions for dashboard advice.
"""
import os
import json
import time
import xgboost as xgb
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from sqlalchemy import select, desc
from datetime import datetime

# Resolve backend/app as BASE_DIR so model files can be found regardless of the
# current working directory used by API routes or scripts.
import sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from app.core.db import AsyncSessionLocal
from app.models.all_models import Asset, PriceHistory, Sentiment
from app.core.symbols import normalize_symbol

class XGBoostInferenceEngine:
    """
    Loads XGBoost model artifacts and produces prediction records for dashboard advice.

    The engine reports unavailable/error states honestly when artifacts or data are
    missing, so recommendation logic can treat the model as a weak signal only.
    """
    def __init__(self):
        # Production model artifacts copied into the backend service directory.
        self.model_dir = os.path.join(BASE_DIR, "app", "services", "ai_engine", "models")
        self.model_path = os.path.join(self.model_dir, "xgboost_apex.json")
        self.binary_model_path = os.path.join(self.model_dir, "xgboost_binary.json")
        self.features_path = os.path.join(self.model_dir, "xgboost_feature_columns.json")
        
        # Training metrics live outside the backend package and are used only
        # for honest model-status reporting.
        self.metrics_path = os.path.join(BASE_DIR, "..", "data", "training", "artifacts", "xgboost_metrics.json")
        
        self.model = None
        self.binary_model = None
        self.feature_cols = []
        self.is_loaded = False
        self.metrics = {}
        
        self._load_resources()

    def _load_resources(self):
        """
        Load model weights, feature columns, and validation metrics.

        Missing artifacts disable inference instead of creating placeholder
        predictions, allowing recommendation logic to fall back honestly.
        """
        if os.path.exists(self.model_path) and os.path.exists(self.features_path):
            try:
                self.model = xgb.XGBClassifier()
                self.model.load_model(self.model_path)
                
                if os.path.exists(self.binary_model_path):
                    self.binary_model = xgb.XClassifier() if hasattr(xgb, 'XClassifier') else xgb.XGBClassifier()
                    self.binary_model.load_model(self.binary_model_path)
                
                with open(self.features_path, 'r') as f:
                    self.feature_cols = json.load(f)
                
                if os.path.exists(self.metrics_path):
                    with open(self.metrics_path, 'r') as f:
                        self.metrics = json.load(f)
                
                self.is_loaded = True
            except Exception as e:
                print(f"XGBoost Engine Load Error: {e}")
        else:
            print(f"XGBoost artifacts missing at {self.model_dir}. Inference disabled.")

    async def _fetch_history(self, symbol: str, limit: int = 250) -> pd.DataFrame:
        """
        Fetch recent price history for one normalized ticker from the database.

        The returned DataFrame is ordered chronologically because feature
        engineering depends on rolling windows and lagged returns.
        """
        normalized = normalize_symbol(symbol)
        async with AsyncSessionLocal() as session:
            asset_res = await session.execute(select(Asset).where(Asset.ticker == normalized))
            asset = asset_res.scalar_one_or_none()
            if not asset:
                return pd.DataFrame()
            
            stmt = (
                select(PriceHistory)
                .where(PriceHistory.asset_id == asset.id)
                .order_by(desc(PriceHistory.timestamp))
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            if not rows:
                return pd.DataFrame()
            
            data = [{"timestamp": r.timestamp, "close": r.price, "volume": r.volume} for r in rows]
            df = pd.DataFrame(data).sort_values("timestamp")
            return df

    def _engineer_features(self, df: pd.DataFrame, ticker: str, sentiment_score: float = 0.0) -> pd.DataFrame:
        """
        Recreate the training feature vector for one latest market row.

        Inputs are price history, ticker, and latest sentiment score; output is a
        single-row DataFrame aligned to the stored feature column order.
        """
        if df.empty or len(df) < 50:
            return pd.DataFrame()

        df = df.copy()
        # Lagged returns capture recent momentum over multiple horizons.
        for p in [1, 3, 5, 10, 20]:
            df[f'return_{p}'] = df['close'].pct_change(p)
            
        # Moving-average gaps encode distance from short and medium trend levels.
        for p in [5, 10, 20, 50]:
            df[f'sma_{p}_gap_pct'] = (df['close'] / df['close'].rolling(p).mean()) - 1.0
        for p in [10, 20]:
            df[f'ema_{p}_gap_pct'] = (df['close'] / df['close'].ewm(span=p, adjust=False).mean()) - 1.0
            
        # RSI-style oscillator based on a 14-period gain/loss window.
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # MACD normalized by price to keep features comparable across assets.
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd_pct'] = (ema12 - ema26) / (df['close'] + 1e-9)
        
        # Rolling volatility features capture short-term instability.
        df['volatility_10'] = df['return_1'].rolling(10).std()
        df['volatility_20'] = df['return_1'].rolling(20).std()
        
        # Z-scores normalize price/volume against recent local history.
        df['close_zscore_20'] = (df['close'] - df['close'].rolling(20).mean()) / (df['close'].rolling(20).std() + 1e-9)
        df['volume_zscore_20'] = (df['volume'] - df['volume'].rolling(20).mean()) / (df['volume'].rolling(20).std() + 1e-9)
        df['finbert_score'] = sentiment_score
        
        # Use only the latest row and rebuild categorical one-hot columns.
        last_row = df.iloc[[-1]].copy()
        norm_ticker = normalize_symbol(ticker)
        
        # Match the asset-type mapping used by the training dataset.
        asset_type = "equity"
        if "/" in norm_ticker: asset_type = "forex"
        if norm_ticker in ["BTC/USD", "ETH/USD"]: asset_type = "crypto"
        if norm_ticker in ["BRENT", "WTI", "XAU/USD", "XAG/USD"]: asset_type = "commodity"

        for col in self.feature_cols:
            if col.startswith("sym_"):
                last_row[col] = 1 if col == f"sym_{norm_ticker}" else 0
            elif col.startswith("type_"):
                last_row[col] = 1 if col == f"type_{asset_type}" else 0
            elif col not in last_row.columns:
                last_row[col] = 0.0
                
        X_df = last_row[self.feature_cols]
        # Replace non-finite values so XGBoost receives a numeric feature vector.
        X_df = X_df.replace([np.inf, -np.inf], 0.0).fillna(0.0)
        return X_df

    async def predict(self, ticker: str) -> Dict[str, Any]:
        """
        Run XGBoost inference for one asset using DB history and latest sentiment.

        Returns a structured success, unavailable, or error payload so callers
        can decide whether to use the model as a weak signal in recommendations.
        """
        if not self.is_loaded:
            return {"status": "unavailable", "reason": "XGBoost model not loaded."}
            
        df = await self._fetch_history(ticker)
        if df.empty or len(df) < 50:
            return {"status": "unavailable", "reason": f"Insufficient history for {ticker}."}
            
        sentiment_score = 0.0
        sentiment_source = "neutral_no_recent_news"
        
        normalized = normalize_symbol(ticker)
        async with AsyncSessionLocal() as session:
            asset_res = await session.execute(select(Asset).where(Asset.ticker == normalized))
            asset = asset_res.scalar_one_or_none()
            if asset:
                sent_res = await session.execute(
                    select(Sentiment).where(Sentiment.asset_id == asset.id).order_by(desc(Sentiment.created_at)).limit(1)
                )
                sent = sent_res.scalar_one_or_none()
                if sent and sent.score is not None:
                    sentiment_score = float(sent.score)
                    sentiment_source = "database_sentiment"

        try:
            X_df = self._engineer_features(df, ticker, sentiment_score=sentiment_score)
            if X_df.empty:
                return {"status": "error", "reason": "Feature engineering failed."}
                
            probs = self.model.predict_proba(X_df.values)[0]
            labels = ["Bearish", "Neutral", "Bullish"]
            pred_idx = int(np.argmax(probs))
            
            binary_prediction = None
            binary_confidence = None
            if self.binary_model:
                bin_probs = self.binary_model.predict_proba(X_df.values)[0]
                bin_labels = ["DOWN", "UP"]
                bin_pred_idx = int(np.argmax(bin_probs))
                binary_prediction = bin_labels[bin_pred_idx]
                binary_confidence = float(bin_probs[bin_pred_idx])
            
            latest = df.iloc[-1]
            process_ts = time.time()
            
            ts = latest["timestamp"]
            ingest_ts = ts.timestamp() if hasattr(ts, "timestamp") else float(ts)
            
            return {
                "status": "success",
                "ticker": ticker,
                "prediction": labels[pred_idx],
                "confidence": float(probs[pred_idx]),
                "probabilities": {labels[i]: float(probs[i]) for i in range(3)},
                "binary_prediction": binary_prediction,
                "binary_confidence": binary_confidence,
                "sentiment_score": sentiment_score,
                "sentiment_source": sentiment_source,
                "source": "database_price_history",
                "history_rows": len(df),
                "price": float(latest["close"]),
                "ingest_ts": ingest_ts,
                "process_ts": process_ts,
                "feature_columns_count": len(self.feature_cols),
                "model_path": self.model_path
            }
        except Exception as e:
            return {"status": "error", "reason": str(e)}

# Shared inference engine instance used by API routes and recommender logic.
xgboost_engine = XGBoostInferenceEngine()
