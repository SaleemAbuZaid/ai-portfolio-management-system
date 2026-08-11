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
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_step12_validation_endpoint(controlled_client: AsyncClient):
    """
    Verifies that the Step 12 Validation endpoint returns the required structure.
    """
    response = await controlled_client.get("/api/v1/metrics/step12-validation")
    assert response.status_code == 200
    data = response.json()
    
    # Assert structural keys exist
    expected_keys = [
        "pytest_status", "total_tests", "passed_tests", "failed_tests",
        "backtest_status", "trades_executed", "buy_count", "sell_count",
        "data_points_used", "step11_regression_status", "generated_at"
    ]
    for key in expected_keys:
        assert key in data, f"Missing key: {key}"
    
    # Assert types (if not run yet, they might be default values)
    assert isinstance(data["total_tests"], int)
    assert isinstance(data["passed_tests"], int)
    assert isinstance(data["trades_executed"], int)
