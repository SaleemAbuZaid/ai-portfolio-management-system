"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Normalizes asset symbols across providers, cache keys, APIs, and dashboard display.
"""
SYMBOL_ALIASES = {
    "BTCUSDT": "BTC/USD",
    "BTCUSD": "BTC/USD",
    "ETHUSDT": "ETH/USD",
    "ETHUSD": "ETH/USD",
    "XAUUSD": "XAU/USD",
    "XAGUSD": "XAG/USD",
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDTRY": "USD/TRY",
    "USDJPY": "USD/JPY",
    "WTI/USD": "WTI",
    "BRENT/USD": "BRENT",
}

def normalize_symbol(symbol: str) -> str:
    """
    Standardizes ticker symbols across the platform (TwelveData, AlphaVantage, Polygon, etc.)
    to a unified 'ASSET/BASE' or standard ticker format used in the training dataset.
    """
    if not symbol:
        return symbol
    
    # Uppercase and strip
    s = symbol.upper().strip()
    
    # Direct lookup in aliases
    if s in SYMBOL_ALIASES:
        return SYMBOL_ALIASES[s]
    
    return s

TRACKED_ASSETS = [
    "AAPL", "TSLA", 
    "BTC/USD", "ETH/USD", 
    "EUR/USD", "GBP/USD", 
    "USD/TRY", "USD/JPY", 
    "XAU/USD", "XAG/USD", 
    "WTI", "BRENT"
]
