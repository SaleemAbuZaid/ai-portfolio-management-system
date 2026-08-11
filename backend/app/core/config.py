"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Loads environment-backed settings and masks credential presence for safe health reporting.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional

# Resolve the repository root so .env loading works from API routes, tests, and scripts.
BASE_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = BASE_DIR / ".env"

def mask_key(key: str) -> str:
    """Mask a credential for health responses without exposing the raw value."""
    if not key or len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"

class Settings(BaseSettings):
    """
    Environment-backed application settings.

    Values are loaded from environment/.env at runtime and are referenced by
    API routes, provider adapters, workers, and tests without exposing secrets.
    """
    # App config
    PROJECT_NAME: str = "Apex AI Trading"
    VERSION: str = "2.1.0"
    PORT: int = 8000
    DEBUG: bool = False
    LIVE_VERIFY_MODE: bool = True
    STEP12_VALIDATION_MODE: bool = True
    ENABLE_NEWS_BACKUP_MODE: bool = False
    
    # Authentication (Phase 3)
    JWT_SECRET: str = "" # Expected from environment
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 # 24 hours for defense ease
    
    # Execution
    # TRADING_MODE can be LIVE or PAPER
    TRADING_MODE: str = "PAPER"
    
    # Connections
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    
    # Broker (Alpaca Paper Trading)
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    ALPACA_URL: str = "https://paper-api.alpaca.markets"
    
    # Database Configuration
    DATABASE_URL: str = "sqlite+aiosqlite:///./apex_trading.db"

    # API Keys (Institutional Connectors)
    ALPHAVANTAGE_API_KEY: str = ""
    POLYGON_API_KEY: str = ""
    COINGECKO_API_KEY: str = ""
    COINGECKO_PLAN: str = "internal"
    MARKETAUX_API_KEY: str = ""
    EVENTREGISTRY_API_KEY: str = ""
    TWELVEDATA_API_KEY: str = ""
    
    # Infrastructure & Specialized WSS URLs
    BINANCE_WSS_URL: str = "wss://stream.binance.com:9443/stream"
    
    # Feature Flags & Live Connectors
    ENABLE_LIVE_MARKET_DATA: bool = True
    ENABLE_ENRICHMENT: bool = True
    ENABLE_LIVE_NEWS: bool = True
    
    # Latency & Health
    STALE_DATA_THRESHOLD_MS: int = 10000
    LOG_LEVEL: str = "INFO"

    # NLP
    FINBERT_MODEL_NAME: str = "ProsusAI/finbert"
    BYPASS_NLP: bool = True  # Set to True for Graduation Defense to avoid heavy downloads

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="allow",
        case_sensitive=False
    )

    @property
    def get_alpaca_url(self) -> str:
        if self.TRADING_MODE.upper() == "PAPER":
            return "https://paper-api.alpaca.markets"
        return self.ALPACA_URL

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.TRADING_MODE.upper() == "PAPER":
            self.ALPACA_URL = "https://paper-api.alpaca.markets"
            
        # Authentication must never start with a shared or hard-coded secret.
        if not self.JWT_SECRET:
            raise ValueError("JWT_SECRET must be set in the environment or .env file")

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
