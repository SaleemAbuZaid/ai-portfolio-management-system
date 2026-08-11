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

@pytest.mark.asyncio
async def test_get_market_data_aapl(controlled_client):
    """Verify market data structure for AAPL."""
    response = await controlled_client.get("/api/v1/market/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert "latest_price" in data
    assert "source" in data
    assert "timestamp" in data
