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
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# Set paths
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT_DIR, "data", "training", "intraday_validation.parquet")
CSV_PATH = os.path.join(ROOT_DIR, "data", "training", "intraday_validation.csv")
os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)

# Map our internal symbols to yfinance symbols
YF_SYMBOL_MAP = {
    "AAPL": "AAPL",
    "TSLA": "TSLA",
    "BTC/USD": "BTC-USD",
    "ETH/USD": "ETH-USD",
    "XAU/USD": "GC=F",   # Gold Futures
    "XAG/USD": "SI=F",   # Silver Futures
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/TRY": "USDTRY=X",
    "USD/JPY": "USDJPY=X",
    "WTI": "CL=F",       # Crude Oil
    "BRENT": "BZ=F"      # Brent Crude
}

def build_intraday_data(symbols, interval="1h", period="60d"):
    print(f"=== Building Intraday Validation Dataset ===")
    print(f"Interval: {interval}, Period: {period}")
    
    all_dfs = []
    
    for symbol in symbols:
        yf_sym = YF_SYMBOL_MAP.get(symbol, symbol)
        print(f"Fetching {yf_sym} ({symbol})...", end=" ")
        
        try:
            ticker = yf.Ticker(yf_sym)
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                print("No data.")
                continue
                
            print(f"Got {len(df)} rows.")
            
            # Standardize columns
            df = df.reset_index()
            # YFinance returns Datetime as index
            date_col = df.columns[0]
            df = df.rename(columns={
                date_col: 'timestamp',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })
            
            df['symbol'] = symbol
            
            # Add basic indicators
            df['return_1'] = df['close'].pct_change()
            df['sma_10'] = df['close'].rolling(window=10).mean()
            
            # RSI Calculation
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi_14'] = 100 - (100 / (1 + rs))
            
            df['volatility_10'] = df['close'].rolling(window=10).std()
            
            # Target logic (e.g., predict next 1-hour return)
            df['future_return_1'] = df['close'].shift(-1) / df['close'] - 1
            
            # Drop NaNs
            df = df.dropna()
            
            # Ensure timestamp is tz-naive or UTC string for parquet compatibility
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.strftime('%Y-%m-%d %H:%M:%S')
            
            all_dfs.append(df)
        except Exception as e:
            print(f"Error: {e}")
            
    if not all_dfs:
        print("Failed to fetch any data.")
        return
        
    final_df = pd.concat(all_dfs, ignore_index=True)
    
    # Save
    final_df.to_parquet(DATA_PATH, index=False)
    final_df.to_csv(CSV_PATH, index=False)
    
    print(f"\nSaved {len(final_df)} rows to:")
    print(f" - {DATA_PATH}")
    print(f" - {CSV_PATH}")

if __name__ == "__main__":
    build_intraday_data(list(YF_SYMBOL_MAP.keys()), interval="1h", period="60d")
