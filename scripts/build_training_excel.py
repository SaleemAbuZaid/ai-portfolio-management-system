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
import os
import time
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# API Keys
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")

# Asset Basket
ASSETS = [
    "AAPL", "TSLA", "BTC/USD", "ETH/USD", "XAU/USD", "XAG/USD", 
    "EUR/USD", "GBP/USD", "USD/TRY", "USD/JPY", "USO", "BNO"
]

def fetch_historical_data(symbol, interval='1h', outputsize=200):
    """Fetch historical OHLCV data from Twelve Data."""
    logger.info(f"Fetching historical data for {symbol}...")
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={TWELVEDATA_API_KEY}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if "values" not in data:
            logger.error(f"Error fetching {symbol}: {data.get('message', 'Unknown error')}")
            return None
            
        df = pd.DataFrame(data["values"])
        df['datetime'] = pd.to_datetime(df['datetime'])
        
        # Make volume optional
        if 'volume' not in df.columns:
            df['volume'] = 0
            
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
        df = df.dropna(subset=['close']) # Ensure we have close price
        df = df.sort_values('datetime').reset_index(drop=True)
        df['symbol'] = symbol
        return df
    except Exception as e:
        logger.error(f"Exception fetching {symbol}: {e}")
        return None

def calculate_indicators(df):
    """Calculate technical indicators."""
    if df is None or len(df) < 30:
        return df
        
    # Returns
    df['return_1'] = df['close'].pct_change(1)
    df['return_3'] = df['close'].pct_change(3)
    df['return_5'] = df['close'].pct_change(5)
    
    # SMAs
    df['sma_5'] = df['close'].rolling(window=5).mean()
    df['sma_10'] = df['close'].rolling(window=10).mean()
    df['sma_20'] = df['close'].rolling(window=20).mean()
    
    # EMA
    df['ema_10'] = df['close'].ewm(span=10, adjust=False).mean()
    
    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    # MACD
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    
    # Volatility (10)
    df['volatility_10'] = df['return_1'].rolling(window=10).std()
    
    return df

def fetch_news_sentiment(symbol):
    """Fetch recent news sentiment from Alpha Vantage."""
    # Alpha Vantage uses simple tickers
    av_symbol = symbol.split('/')[0] if '/' in symbol else symbol
    logger.info(f"Fetching news sentiment for {av_symbol}...")
    
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={av_symbol}&apikey={ALPHAVANTAGE_API_KEY}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        feed = data.get("feed", [])
        if not feed:
            return 0.0, "NEUTRAL"
            
        # Average sentiment of the latest few articles
        scores = [float(item.get("overall_sentiment_score", 0)) for item in feed[:5]]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        # Determine event type (simplified)
        event_type = "GENERAL"
        if "central bank" in str(feed[0]).lower(): event_type = "MACRO"
        elif "earnings" in str(feed[0]).lower(): event_type = "EARNINGS"
        
        return avg_score, event_type
    except Exception as e:
        logger.error(f"Error fetching news for {symbol}: {e}")
        return 0.0, "NONE"

def apply_target_logic(df):
    """Apply future return and direction labels."""
    if df is None or len(df) < 6:
        return df
        
    # future_return = close(t+5) / close(t) - 1
    df['target_return'] = df['close'].shift(-5) / df['close'] - 1
    
    # target_direction logic
    # 1 if future_return > 0.002
    # 0 if -0.002 <= future_return <= 0.002
    # -1 if future_return < -0.002
    
    def label_direction(ret):
        if pd.isna(ret): return np.nan
        if ret > 0.002: return 1
        if ret < -0.002: return -1
        return 0
        
    df['target_direction'] = df['target_return'].apply(label_direction)
    return df

def main():
    # Ensure data directory exists
    os.makedirs("data/training", exist_ok=True)
    
    all_data = []
    
    for symbol in ASSETS:
        # 1. Fetch Price Data
        df = fetch_historical_data(symbol)
        if df is None: continue
        
        # 2. Calculate Indicators
        df = calculate_indicators(df)
        
        # 3. Apply Targets
        df = apply_target_logic(df)
        
        # 4. Add Sentiment (Static for historical backfill to avoid API blowup)
        # In a real scenario, we'd align per timestamp. Here we use a representative value.
        sentiment_score, event_type = fetch_news_sentiment(symbol)
        df['news_sentiment_score'] = sentiment_score
        df['news_event_type'] = event_type
        
        # Rename columns to match requested Excel headers
        df = df.rename(columns={'datetime': 'timestamp'})
        
        # Reorder columns to match request
        cols = [
            'timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume',
            'return_1', 'return_3', 'return_5', 'sma_5', 'sma_10', 'sma_20',
            'ema_10', 'rsi_14', 'macd', 'volatility_10', 
            'news_sentiment_score', 'news_event_type',
            'target_direction', 'target_return'
        ]
        # Keep only existing columns
        existing_cols = [c for c in cols if c in df.columns]
        df = df[existing_cols]
        
        all_data.append(df)
        
        # Respect API Limits
        time.sleep(20) # Twelve Data free limit is 8/min, increase buffer
        
    if not all_data:
        logger.error("No data collected.")
        return
        
    # Combine and Save
    final_df = pd.concat(all_data, ignore_index=True)
    output_path = "data/training/market_training.xlsx"
    final_df.to_excel(output_path, index=False)
    logger.info(f"Excel generated successfully at {output_path}")

if __name__ == "__main__":
    main()
