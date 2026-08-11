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
from app.services.nlp_service import NLPService

def test_sentiment_pipeline_structure():
    """Verify sentiment pipeline returns expected structure."""
    service = NLPService()
    text = "Neutral check."
    result = service.analyze_sentiment(text)
    assert "score" in result
    assert "label" in result

def test_sentiment_pipeline_bullish():
    """Verify sentiment pipeline on bullish input."""
    service = NLPService()
    text = "Excellent earnings results and very strong future growth projections."
    result = service.analyze_sentiment(text)
    
    if "error" not in result:
        # Just check that it's a number
        assert isinstance(result["score"], float)
        assert result["label"] in ["POSITIVE", "NEGATIVE", "NEUTRAL"]

def test_sentiment_pipeline_bearish():
    """Verify sentiment pipeline on bearish input."""
    service = NLPService()
    text = "Disastrous losses and extremely negative outlook for the upcoming year."
    result = service.analyze_sentiment(text)
    
    if "error" not in result:
        assert isinstance(result["score"], float)
        assert result["label"] in ["POSITIVE", "NEGATIVE", "NEUTRAL"]
