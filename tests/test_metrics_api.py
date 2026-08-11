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
async def test_get_performance_metrics(controlled_client):
    """Verify performance metrics endpoint structure."""
    response = await controlled_client.get("/api/v1/metrics/performance")
    assert response.status_code == 200
    data = response.json()
    required_keys = [
        "total_requests", 
        "cache_hits", 
        "cache_misses", 
        "cache_hit_rate", 
        "average_latency_ms", 
        "p95_latency_ms", 
        "error_rate"
    ]
    for key in required_keys:
        assert key in data
