"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Defines domain schemas shared by portfolio, market, and AI API responses.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import uuid4

class TickData(BaseModel):
    """Normalized market tick shape passed between ingestion and workers."""
    ticker: str = Field(..., alias="symbol") # Accept symbol/ticker interchangeably.
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[float] = None
    provider: str = "internal"
    provider_ts: float = Field(default_factory=lambda: 0.0, description="Timestamp from the data provider")
    ingest_ts: float = Field(default_factory=lambda: 0.0, description="Timestamp when system received the tick")
    asset_type: str = "crypto"
    sequence_ref: Optional[str] = None

    class Config:
        populate_by_name = True

class NewsEvent(BaseModel):
    """Normalized news event shape published into NLP/recommendation flows."""
    article_id: str = Field(default_factory=lambda: str(uuid4()))
    headline: str
    url: Optional[str] = None
    summary: Optional[str] = None
    sentiment_score: float = 0.0
    confidence: float = 1.0
    source: str = "Unknown"
    source_ts: float = Field(default_factory=lambda: 0.0)
    ingest_ts: float = Field(default_factory=lambda: 0.0)
    symbols: List[str] = []
    topics: List[str] = []
    macro_impact: Dict[str, Any] = {}

class AISignal(BaseModel):
    """AI recommendation signal consumed by the execution worker."""
    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    asset_id: Optional[Any] = None
    ticker: str
    action: str  # BUY, SELL, HOLD, WATCH, AVOID
    confidence: float
    tech_score: float = 0.0
    sent_score: float = 0.0
    forecast_score: float = 0.0
    risk_score: float = 0.0
    reasoning: str
    provider_ts: Optional[float] = None
    ingest_ts: Optional[float] = None
    process_ts: Optional[float] = None
    signal_ts: float = Field(default_factory=lambda: 0.0)
    model_version: str = "v2.0-resilience"

    model_config = {
        "protected_namespaces": ()
    }
