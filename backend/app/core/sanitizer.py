"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Normalizes provider names before they are shown in provenance labels.
"""
from typing import Optional
import logging

ALLOWED_PROVIDERS = {
    "ALPHAVANTAGE",
    "TWELVEDATA",
    "ALPACA",
    "ALPACA PAPER",
    "COINGECKO",
    "BINANCE",
    "LIVE_PROVIDER",
    "DELAYED_PROVIDER",
    "DELAYED_DB",
    "HISTORY_DB",
    "INTERNAL_FALLBACK",
    "MISSING"
}

def sanitize_provider_name(provider_name: Optional[str]) -> str:
    """
    Normalizes provider names to standard labels.
    If the provider is not in the ALLOWED_PROVIDERS list, it returns 'INTERNAL_FALLBACK'.
    """
    if not provider_name:
        return "INTERNAL_FALLBACK"
        
    # Convert to uppercase immediately
    upper_name = str(provider_name).strip().upper()
    
    # Explicit mapping for common variations
    mapping = {
        "ALPHAVANTAGE": "ALPHAVANTAGE",
        "TWELVEDATA": "TWELVEDATA",
        "ALPACA": "ALPACA",
        "ALPACA PAPER": "ALPACA PAPER",
        "COINGECKO": "COINGECKO",
        "BINANCE": "BINANCE",
        "INTERNAL": "INTERNAL_FALLBACK",
        "FALLBACK": "INTERNAL_FALLBACK",
        "HISTORICAL DB": "HISTORY_DB",
        "HISTORICAL": "HISTORY_DB",
        "DB": "HISTORY_DB",
        "N/A": "INTERNAL_FALLBACK",
        "UNKNOWN": "INTERNAL_FALLBACK"
    }
    
    if upper_name in mapping:
        return mapping[upper_name]
        
    # Check for partial matches or fuzzy mappings
    if "ALPACAPAPER" in upper_name.replace(" ", ""):
        return "ALPACA PAPER"
    if "ALPHAVANTAGE" in upper_name:
        return "ALPHAVANTAGE"
    if "TWELVEDATA" in upper_name:
        return "TWELVEDATA"
        
    if upper_name in ALLOWED_PROVIDERS:
        return upper_name
        
    return "INTERNAL_FALLBACK"
