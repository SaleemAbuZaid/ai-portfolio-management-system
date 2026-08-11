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
import yfinance as yf
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# API Keys
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")

ASSETS = [
    "AAPL", "TSLA", "BTC/USD", "ETH/USD", "XAU/USD", "XAG/USD", 
    "EUR/USD", "GBP/USD", "USD/TRY", "USD/JPY", "WTI", "BRENT"
]

def map_symbol_to_polygon(symbol):
    if "/" in symbol:
        if symbol.startswith("XAU") or symbol.startswith("XAG") or symbol.startswith("EUR") or symbol.startswith("GBP") or symbol.startswith("USD"):
            return f"C:{symbol.replace('/', '')}"
        elif symbol.startswith("BTC") or symbol.startswith("ETH"):
            return f"X:{symbol.replace('/', '')}"
    if symbol == "WTI": return None
    if symbol == "BRENT": return None
    return symbol

def map_symbol_to_alphavantage(symbol):
    if symbol == "WTI": return "WTI"
    if symbol == "BRENT": return "BRENT"
    if "/" in symbol:
        return symbol.split("/")[0]
    return symbol

def map_symbol_to_twelvedata(symbol):
    return symbol

def map_symbol_to_yfinance(symbol):
    if symbol == "BTC/USD": return "BTC-USD"
    if symbol == "ETH/USD": return "ETH-USD"
    if symbol == "EUR/USD": return "EURUSD=X"
    if symbol == "GBP/USD": return "GBPUSD=X"
    if symbol == "USD/TRY": return "USDTRY=X"
    if symbol == "USD/JPY": return "USDJPY=X"
    if symbol == "XAU/USD": return "GC=F"
    if symbol == "XAG/USD": return "SI=F"
    if symbol == "WTI": return "CL=F"
    if symbol == "BRENT": return "BZ=F"
    return symbol

def fetch_polygon(symbol, start_date, end_date):
    poly_sym = map_symbol_to_polygon(symbol)
    if not poly_sym or not POLYGON_API_KEY:
        return None
    url = f"https://api.polygon.io/v2/aggs/ticker/{poly_sym}/range/1/day/{start_date}/{end_date}?adjusted=true&sort=asc&limit=50000&apiKey={POLYGON_API_KEY}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get('resultsCount', 0) > 0:
                df = pd.DataFrame(data['results'])
                df['timestamp'] = pd.to_datetime(df['t'], unit='ms')
                df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)
                df['market_provider'] = 'Polygon.io'
                df['source_symbol'] = poly_sym
                return df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'market_provider', 'source_symbol']]
    except Exception as e:
        pass
    return None

def fetch_alphavantage(symbol):
    av_sym = map_symbol_to_alphavantage(symbol)
    if not av_sym or not ALPHAVANTAGE_API_KEY:
        return None
    if "/" in symbol:
        if symbol.startswith("BTC") or symbol.startswith("ETH"):
            url = f"https://www.alphavantage.co/query?function=DIGITAL_CURRENCY_DAILY&symbol={av_sym}&market=USD&apikey={ALPHAVANTAGE_API_KEY}"
            key_name = "Time Series (Digital Currency Daily)"
        else:
            from_sym, to_sym = symbol.split("/")
            url = f"https://www.alphavantage.co/query?function=FX_DAILY&from_symbol={from_sym}&to_symbol={to_sym}&outputsize=full&apikey={ALPHAVANTAGE_API_KEY}"
            key_name = "Time Series FX (Daily)"
    else:
        url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={av_sym}&outputsize=full&apikey={ALPHAVANTAGE_API_KEY}"
        key_name = "Time Series (Daily)"

    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if "Note" in data or "Information" in data:
                return None
            if key_name in data:
                ts = data[key_name]
                df = pd.DataFrame.from_dict(ts, orient='index')
                df.index = pd.to_datetime(df.index)
                df = df.reset_index().rename(columns={'index': 'timestamp'})
                col_map = {}
                for col in df.columns:
                    if 'open' in col.lower(): col_map[col] = 'open'
                    elif 'high' in col.lower(): col_map[col] = 'high'
                    elif 'low' in col.lower(): col_map[col] = 'low'
                    elif 'close' in col.lower() and 'usd' not in col.lower(): col_map[col] = 'close'
                    elif 'volume' in col.lower(): col_map[col] = 'volume'
                if "4b. close (USD)" in df.columns:
                    col_map["4b. close (USD)"] = "close"
                df.rename(columns=col_map, inplace=True)
                for c in ['open', 'high', 'low', 'close', 'volume']:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c])
                    else:
                        df[c] = 0.0
                df['market_provider'] = 'Alpha Vantage'
                df['source_symbol'] = av_sym
                return df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'market_provider', 'source_symbol']].sort_values('timestamp')
    except Exception as e:
        pass
    return None

def fetch_twelvedata(symbol):
    td_sym = map_symbol_to_twelvedata(symbol)
    if not td_sym or not TWELVEDATA_API_KEY:
        return None
    url = f"https://api.twelvedata.com/time_series?symbol={td_sym}&interval=1day&outputsize=5000&apikey={TWELVEDATA_API_KEY}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if "values" in data:
                df = pd.DataFrame(data["values"])
                df['timestamp'] = pd.to_datetime(df['datetime'])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col])
                    else:
                        df[col] = 0.0
                df['market_provider'] = 'Twelve Data'
                df['source_symbol'] = td_sym
                return df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'market_provider', 'source_symbol']].sort_values('timestamp')
            elif data.get("code") == 429:
                time.sleep(1)
    except Exception as e:
        pass
    return None

def fetch_yfinance(symbol):
    yf_sym = map_symbol_to_yfinance(symbol)
    try:
        ticker = yf.Ticker(yf_sym)
        df = ticker.history(period="max")
        if not df.empty:
            df = df.reset_index()
            date_col = 'Date' if 'Date' in df.columns else 'Datetime'
            df['timestamp'] = pd.to_datetime(df[date_col]).dt.tz_localize(None)
            df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
            df['market_provider'] = 'Yahoo Finance'
            df['source_symbol'] = yf_sym
            return df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'market_provider', 'source_symbol']]
    except Exception as e:
        pass
    return None

def fetch_best_data(symbol):
    start_date = "2004-01-01"
    end_date = datetime.now().strftime("%Y-%m-%d")
    
    candidates = {}
    
    # Try Polygon
    df_poly = fetch_polygon(symbol, start_date, end_date)
    if df_poly is not None and not df_poly.empty:
        candidates['Polygon.io'] = df_poly
        
    # Try Alpha Vantage
    df_av = fetch_alphavantage(symbol)
    if df_av is not None and not df_av.empty:
        candidates['Alpha Vantage'] = df_av
        
    # Try Twelve Data
    df_td = fetch_twelvedata(symbol)
    if df_td is not None and not df_td.empty:
        candidates['Twelve Data'] = df_td
        
    # Try Yahoo Finance
    df_yf = fetch_yfinance(symbol)
    if df_yf is not None and not df_yf.empty:
        candidates['Yahoo Finance'] = df_yf
        
    if not candidates:
        return None, {}
        
    # Evaluate candidates
    candidate_stats = {}
    for prov, c_df in candidates.items():
        min_date = c_df['timestamp'].min()
        max_date = c_df['timestamp'].max()
        years = (max_date - min_date).days / 365.25
        rows = len(c_df)
        candidate_stats[prov] = {
            'rows': rows,
            'years': years,
            'df': c_df
        }
        
    # Selection priority: Polygon > Alpha Vantage > Twelve Data > Yahoo Finance
    priority = {'Polygon.io': 4, 'Alpha Vantage': 3, 'Twelve Data': 2, 'Yahoo Finance': 1}
    
    best_provider = None
    best_score = -1
    
    for prov, stats in candidate_stats.items():
        years = stats['years']
        rows = stats['rows']
        prov_score = priority.get(prov, 0)
        
        # Calculate a composite score prioritizing coverage years heavily
        score = (years * 10000) + rows + (prov_score * 0.1)
        if score > best_score:
            best_score = score
            best_provider = prov
            
    provider_candidates_checked = list(candidate_stats.keys())
    
    report_info = {
        'candidates_tried': provider_candidates_checked,
        'candidate_stats': {k: {'rows': v['rows'], 'years': v['years']} for k, v in candidate_stats.items()},
        'selected_provider': best_provider,
        'rejected': []
    }
    
    for prov in provider_candidates_checked:
        if prov != best_provider:
            r_rows = candidate_stats[prov]['rows']
            r_years = candidate_stats[prov]['years']
            report_info['rejected'].append({
                'provider': prov,
                'reason': f"Lower score. Had {r_years:.1f} yrs ({r_rows} rows) vs Best {candidate_stats[best_provider]['years']:.1f} yrs ({candidate_stats[best_provider]['rows']} rows)."
            })
            
    best_df = candidate_stats[best_provider]['df'].copy()
    
    # Add transparency columns
    best_df['provider_candidates_checked'] = ", ".join(provider_candidates_checked)
    best_df['first_date'] = best_df['timestamp'].min().strftime('%Y-%m-%d')
    best_df['last_date'] = best_df['timestamp'].max().strftime('%Y-%m-%d')
    best_df['row_count'] = len(best_df)
    best_df['coverage_years'] = candidate_stats[best_provider]['years']
    
    return best_df, report_info

def calculate_technical_features(df):
    if df is None or len(df) < 200:
        return df
        
    df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    
    for period in [1, 3, 5, 10, 20]:
        df[f'return_{period}'] = df['close'].pct_change(period)
        
    for period in [5, 10, 20, 50, 100, 200]:
        df[f'sma_{period}'] = df['close'].rolling(window=period).mean()
        
    for period in [10, 20]:
        df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
        
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    for period in [10, 20]:
        df[f'volatility_{period}'] = df['return_1'].rolling(window=period).std()
        
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(window=14).mean()
    
    df['close_zscore_20'] = (df['close'] - df['sma_20']) / df['close'].rolling(window=20).std()
    
    if df['volume'].sum() > 0:
        vol_mean = df['volume'].rolling(window=20).mean()
        vol_std = df['volume'].rolling(window=20).std()
        df['volume_zscore_20'] = (df['volume'] - vol_mean) / (vol_std + 1e-9)
    else:
        df['volume_zscore_20'] = 0.0
        
    return df

def apply_targets(df):
    if df is None or len(df) < 10:
        return df
        
    for horizon in [1, 5, 10]:
        df[f'future_return_{horizon}'] = df['close'].shift(-horizon) / df['close'] - 1
        
    df['target_return'] = df['future_return_5']
    
    def label_direction(ret):
        if pd.isna(ret): return np.nan
        if ret > 0.002: return 1
        if ret < -0.002: return -1
        return 0
        
    df['target_direction'] = df['target_return'].apply(label_direction)
    return df

def generate_quality_report(df, report_infos, output_path):
    report_lines = [
        "# Training Data Quality Report",
        "",
        "## Overall Overview",
        f"- Total Rows: {len(df):,}",
        f"- Columns: {len(df.columns)}",
        f"- Unique Assets: {df['symbol'].nunique()}",
        "",
        "## Asset Breakdown",
        "| Asset | Provider | Source Symbol | Rows | Min Date | Max Date | Coverage (Yrs) | Missing Targets | Target Dist (Up/Flat/Down) | Warnings |",
        "|-------|----------|---------------|------|----------|----------|----------------|-----------------|----------------------------|----------|"
    ]
    
    json_report = {
        "overall": {
            "total_rows": len(df),
            "columns": len(df.columns),
            "unique_assets": int(df['symbol'].nunique())
        },
        "assets": {}
    }
    
    for symbol in sorted(df['symbol'].unique()):
        sdf = df[df['symbol'] == symbol]
        provider = sdf['market_provider'].iloc[0]
        src_sym = sdf['source_symbol'].iloc[0]
        rows = len(sdf)
        min_d = sdf['timestamp'].min().strftime('%Y-%m-%d')
        max_d = sdf['timestamp'].max().strftime('%Y-%m-%d')
        cov_years = sdf['coverage_years'].iloc[0]
        miss_t = int(sdf['target_direction'].isna().sum())
        
        vc = sdf['target_direction'].value_counts()
        up = int(vc.get(1.0, 0))
        flat = int(vc.get(0.0, 0))
        down = int(vc.get(-1.0, 0))
        dist = f"{up}/{flat}/{down}"
        
        warnings = []
        if cov_years < 5:
            warnings.append("<5 Years History")
        elif cov_years < 10 and symbol not in ["BTC/USD", "ETH/USD"]:
            warnings.append("<10 Years History (Expected 10+)")
            
        warn_str = ", ".join(warnings) if warnings else "None"
        
        rep_info = report_infos.get(symbol, {})
        
        # Get missing value counts for important cols
        missing_counts = sdf[['open', 'high', 'low', 'close', 'volume', 'rsi_14', 'macd']].isna().sum().to_dict()
        missing_counts = {k: int(v) for k, v in missing_counts.items()}
        
        json_report["assets"][symbol] = {
            "provider": provider,
            "source_symbol": src_sym,
            "rows": rows,
            "coverage_years": round(cov_years, 2),
            "warnings": warnings,
            "candidates_tried": rep_info.get("candidates_tried", []),
            "rejected_providers": rep_info.get("rejected", []),
            "target_distribution": {"up": up, "flat": flat, "down": down},
            "missing_values": missing_counts
        }
        
        report_lines.append(f"| {symbol} | {provider} | {src_sym} | {rows:,} | {min_d} | {max_d} | {cov_years:.1f} | {miss_t} | {dist} | {warn_str} |")
        
    report_lines.append("\n## Provider Rejection Log\n")
    for symbol, info in report_infos.items():
        report_lines.append(f"### {symbol}")
        report_lines.append(f"- **Selected**: {info['selected_provider']}")
        report_lines.append(f"- **Tried**: {', '.join(info['candidates_tried'])}")
        for r in info.get("rejected", []):
            report_lines.append(f"  - Rejected {r['provider']}: {r['reason']}")
        report_lines.append("")
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    json_path = output_path.replace(".md", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2)

def main():
    os.makedirs("data/training", exist_ok=True)
    all_dfs = []
    report_infos = {}
    
    print(f"{'Symbol':<10} | {'Selected Provider':<18} | {'Source':<12} | {'Rows':<8} | {'First Date':<12} | {'Last Date':<12} | {'Years':<6} | {'Status'}")
    print("-" * 110)
    
    for symbol in ASSETS:
        df, rep_info = fetch_best_data(symbol)
        
        if df is None:
            print(f"{symbol:<10} | {'None':<18} | {'N/A':<12} | {0:<8} | {'N/A':<12} | {'N/A':<12} | {0:<6} | FAILED")
            continue
            
        report_infos[symbol] = rep_info
        df['symbol'] = symbol
        df['asset_type'] = 'crypto' if '/' in symbol and ('BTC' in symbol or 'ETH' in symbol) else ('forex' if '/' in symbol else ('commodity' if symbol in ['WTI', 'BRENT'] else 'equity'))
        
        df = calculate_technical_features(df)
        df = apply_targets(df)
        
        df['news_sentiment_score'] = 0.0
        df['news_event_type'] = 'NONE'
        df['finbert_label'] = 'NEUTRAL'
        df['finbert_score'] = 0.0
        df['finbert_confidence'] = 0.0
        
        all_dfs.append(df)
        
        # Print summary
        provider = df['market_provider'].iloc[0]
        src_sym = df['source_symbol'].iloc[0]
        rows = len(df)
        f_date = df['first_date'].iloc[0]
        l_date = df['last_date'].iloc[0]
        years = df['coverage_years'].iloc[0]
        status = "OK" if years >= 5 else "SHORT"
        print(f"{symbol:<10} | {provider:<18} | {src_sym:<12} | {rows:<8} | {f_date:<12} | {l_date:<12} | {years:<6.1f} | {status}")
        
        time.sleep(2)
            
    if not all_dfs:
        logger.error("No data successfully compiled.")
        return
        
    final_df = pd.concat(all_dfs, ignore_index=True)
    final_df = final_df.sort_values(by=['symbol', 'timestamp']).reset_index(drop=True)
    
    cols = [
        'timestamp', 'symbol', 'asset_type', 'market_provider', 'source_symbol',
        'provider_candidates_checked', 'first_date', 'last_date', 'row_count', 'coverage_years',
        'open', 'high', 'low', 'close', 'volume',
        'return_1', 'return_3', 'return_5', 'return_10', 'return_20',
        'sma_5', 'sma_10', 'sma_20', 'sma_50', 'sma_100', 'sma_200',
        'ema_10', 'ema_20', 'rsi_14', 'macd', 'macd_signal', 'macd_hist',
        'volatility_10', 'volatility_20', 'atr_14', 'close_zscore_20', 'volume_zscore_20',
        'news_sentiment_score', 'news_event_type', 'finbert_label', 'finbert_score', 'finbert_confidence',
        'future_return_1', 'future_return_5', 'future_return_10', 'target_direction', 'target_return'
    ]
    
    final_df = final_df[cols]
    
    final_df.to_excel("data/training/market_training_long.xlsx", index=False)
    final_df.to_csv("data/training/market_training_long.csv", index=False)
    try:
        final_df.to_parquet("data/training/market_training_long.parquet", index=False)
    except Exception:
        pass
        
    generate_quality_report(final_df, report_infos, "data/training/training_data_quality_report.md")
    print(f"\nTotal Dataset Size: {len(final_df)} rows")
    print("Dataset generation complete!")

if __name__ == "__main__":
    main()
