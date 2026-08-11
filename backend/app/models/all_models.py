"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Defines SQLAlchemy database models for users, portfolios, market data, news, AI signals, and executions.
"""
import uuid
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, BigInteger, ForeignKey, Boolean, JSON, func, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from app.core.db import Base

class User(Base):
    """User account, authentication profile, and role-request state."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100))
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255))
    role = Column(String(20), default="USER") # ADMIN, USER, BROKER
    
    # Broker access is requested here but approved through admin routes.
    requested_role = Column(String(20), nullable=True)
    approval_status = Column(String(20), nullable=True) # PENDING, APPROVED, REJECTED
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    
    is_active = Column(Boolean, default=True)
    gender = Column(String(20), nullable=True) # MALE, FEMALE, OTHER
    avatar_url = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    portfolios = relationship("Portfolio", back_populates="owner")

class Portfolio(Base):
    """Local model portfolio used for allocation and rebalance demonstrations."""
    __tablename__ = "portfolios"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(100), nullable=False)
    risk_profile = Column(String(20), default="MEDIUM") # HIGH, MEDIUM, LOW
    cash = Column(Float, default=100000.0)
    total_value = Column(Float, default=100000.0)
    currency = Column(String(10), default="USD")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    owner = relationship("User", back_populates="portfolios")
    assets = relationship("PortfolioAsset", back_populates="portfolio")

class Asset(Base):
    """Tradable asset metadata shared by market, portfolio, and AI records."""
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(100))
    asset_class = Column(String(20)) # EQUITY, CRYPTO, FX, COMMODITY
    provider = Column(String(50))    # Preferred provider

class PortfolioAsset(Base):
    """Join table storing model portfolio quantities per asset."""
    __tablename__ = "portfolio_assets"
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"))
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"))
    quantity = Column(Float, default=0.0)
    avg_price = Column(Float, default=0.0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    portfolio = relationship("Portfolio", back_populates="assets")
    asset = relationship("Asset")

class PriceHistory(Base):
    """
    Persisted market price history with provider lineage.

    Provider timestamp, ingest timestamp, and lag are stored so API responses
    can distinguish live, delayed, historical, and fallback data sources.
    """
    __tablename__ = "price_history"
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    timestamp = Column(DateTime(timezone=True), primary_key=True, index=True)
    price = Column(Float, nullable=False)
    volume = Column(Float)
    # Lineage fields support source provenance and latency audits.
    provider = Column(String(50))
    provider_ts = Column(Float)
    ingest_ts = Column(Float)
    lag_ms = Column(Float)
    
    __table_args__ = (
        Index('idx_price_history_timestamp', 'timestamp'),
        Index('idx_price_history_asset_ts', 'asset_id', 'timestamp'),
    )

class News(Base):
    """Persisted financial news article with provider and ingestion metadata."""
    __tablename__ = "news"
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(String(100), unique=True, index=True)
    provider = Column(String(50))
    headline = Column(Text, nullable=False)
    url = Column(Text)
    published_at = Column(DateTime(timezone=True), index=True)
    ingest_ts = Column(Float)
    raw_payload = Column(Text)
    
    __table_args__ = (
        Index('idx_news_published_at', 'published_at'),
    )

class Sentiment(Base):
    """NLP sentiment score linked to a news item and optional asset."""
    __tablename__ = "sentiment"
    id = Column(Integer, primary_key=True, index=True)
    news_id = Column(Integer, ForeignKey("news.id", ondelete="CASCADE"), index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    score = Column(Float) # -1.0 to 1.0
    label = Column(String(20)) # BULLISH, BEARISH, NEUTRAL
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_sentiment_news_id', 'news_id'),
    )

class Event(Base):
    """Detected macro or asset-specific event derived from ingested news."""
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"))
    news_id = Column(Integer, ForeignKey("news.id", ondelete="CASCADE"), nullable=True)
    event_type = Column(String(50)) # WHALE_MOVE, EARNINGS, MACRO
    magnitude = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class Prediction(Base):
    """Stored model forecast metadata used by recommendation logic."""
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"))
    model_name = Column(String(50))
    target_price = Column(Float)
    horizon = Column(String(20)) # 1H, 24H, 7D
    confidence = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    ingest_ts = Column(Float)  # When raw data first hit the system
    process_ts = Column(Float) # Start of ML processing

    __table_args__ = (
        Index('idx_prediction_asset_ts', 'asset_id', 'timestamp'),
    )

class Recommendation(Base):
    """Persisted BUY/SELL/HOLD recommendation and explanation."""
    __tablename__ = "recommendations"
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"))
    signal = Column(String(20)) # BUY, SELL, HOLD
    confidence = Column(Float)
    reasoning = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Latency markers trace recommendation timing from ingest to final signal.
    ingest_ts = Column(Float)   # When raw data first hit the system
    process_ts = Column(Float)  # When ML processing started
    signal_ts = Column(Float)   # When final decision was made
    execution_price = Column(Float) # Price at the time signal was generated
    
    # Compact labels used by the dashboard AI overview.
    sentiment_label = Column(String(20)) # BULLISH, BEARISH, NEUTRAL
    sentiment_score = Column(Float)
    prediction_label = Column(String(20)) # UP, DOWN, STABLE
    
    __table_args__ = (
        Index('idx_recommendation_timestamp', 'timestamp'),
    )
    
    asset = relationship("Asset")

class ExecutionLog(Base):
    """Execution ledger row for Alpaca Paper acknowledgements and audit proof."""
    __tablename__ = "execution_logs"
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"))
    signal_id = Column(String(100), nullable=True)
    action = Column(String(20)) # BUY, SELL
    quantity = Column(Float)
    price = Column(Float)
    commission = Column(Float, default=0.0)
    status = Column(String(20), default="PENDING")
    order_id = Column(String(100), nullable=True) # Alpaca Paper provider order UUID.
    provider = Column(String(50), default="Alpaca Paper") # Alpaca Paper, etc.
    
    # Filled details are populated when Alpaca confirms execution.
    filled_qty = Column(Float, nullable=True)
    filled_avg_price = Column(Float, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    filled_at = Column(DateTime(timezone=True), nullable=True)
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    execution_ts = Column(Float) # High-precision timestamp
    ingest_ts = Column(Float)
    process_ts = Column(Float)
    signal_ts = Column(Float)

# Compatibility aliases for older scripts that import legacy model names.
MarketDataRow = PriceHistory
NewsRow = News
AISignalRow = Recommendation
ExecutionLedgerRow = ExecutionLog
