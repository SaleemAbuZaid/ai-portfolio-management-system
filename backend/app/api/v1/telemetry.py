"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Exposes telemetry endpoints used for runtime observability and dashboard checks.
"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/latency")
async def get_system_latency():
    """
    Return a lightweight latency value for dashboard telemetry placeholders.

    Full latency/caching metrics are served by /metrics/performance; this route
    exists for simple runtime checks that need a small payload.
    """
    return {"average_ms": 2150}
