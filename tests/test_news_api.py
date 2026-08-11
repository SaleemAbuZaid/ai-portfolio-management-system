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
async def test_get_latest_news(controlled_client):
    """Verify latest news endpoint structure."""
    response = await controlled_client.get("/api/v1/news/latest")
    assert response.status_code == 200
    data = response.json()
    assert "source" in data
    # Some implementations return articles list, others return count + news list
    assert ("articles" in data) or ("news" in data) or ("count" in data)
