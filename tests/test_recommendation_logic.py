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
import pytest
from app.services.ai_engine.recommender import RecommenderService

@pytest.mark.asyncio
async def test_recommendation_logic_bullish(monkeypatch):
    """Verify BUY signal on positive forecast and sentiment."""
    service = RecommenderService()
    
    async def controlled_signals(self, asset_id):
        return {
            "prediction": {"target_price": 220.0, "timestamp": 12345, "ingest_ts": 123, "process_ts": 124},
            "sentiment": {"score": 0.8, "label": "POSITIVE"},
            "event": None,
            "current_price": 200.0
        }
    
    async def controlled_persist(*args, **kwargs):
        return {"action": args[2]}
    
    monkeypatch.setattr(RecommenderService, "get_latest_signals", controlled_signals)
    monkeypatch.setattr(RecommenderService, "_persist_recommendation", controlled_persist)

    result = await service.generate_recommendation(asset_id=1)
    assert result["action"] == "BUY"

@pytest.mark.asyncio
async def test_recommendation_logic_bearish(monkeypatch):
    """Verify SELL signal on negative forecast and sentiment."""
    service = RecommenderService()
    
    async def controlled_signals(self, asset_id):
        return {
            "prediction": {"target_price": 180.0, "timestamp": 12345, "ingest_ts": 123, "process_ts": 124},
            "sentiment": {"score": -0.8, "label": "NEGATIVE"},
            "event": None,
            "current_price": 200.0
        }
    
    async def controlled_persist(*args, **kwargs):
        return {"action": args[2]}
    
    monkeypatch.setattr(RecommenderService, "get_latest_signals", controlled_signals)
    monkeypatch.setattr(RecommenderService, "_persist_recommendation", controlled_persist)

    result = await service.generate_recommendation(asset_id=1)
    assert result["action"] == "SELL"

@pytest.mark.asyncio
async def test_recommendation_logic_neutral(monkeypatch):
    """Verify HOLD signal on neutral/mixed signals."""
    service = RecommenderService()
    
    async def controlled_signals(self, asset_id):
        return {
            "prediction": {"target_price": 201.0, "timestamp": 12345, "ingest_ts": 123, "process_ts": 124},
            "sentiment": {"score": 0.05, "label": "NEUTRAL"},
            "event": None,
            "current_price": 200.0
        }
    
    async def controlled_persist(*args, **kwargs):
        return {"action": args[2]}
    
    monkeypatch.setattr(RecommenderService, "get_latest_signals", controlled_signals)
    monkeypatch.setattr(RecommenderService, "_persist_recommendation", controlled_persist)

    result = await service.generate_recommendation(asset_id=1)
    assert result["action"] == "HOLD"
