"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Defines broker execution request and acknowledgement schemas.
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime

class OrderRequest(BaseModel):
    """
    Standardized payload for dispatching paper or live orders.
    """
    symbol: str
    side: str  # BUY, SELL
    qty: float
    order_type: str = "market"
    time_in_force: str = "day"
    signal_id: Optional[str] = None
    strategy_tag: Optional[str] = None

class OrderAck(BaseModel):
    """
    Broker acknowledgment of an order payload.
    """
    order_id: str
    symbol: str
    side: str
    qty: float
    status: str
    request_ts: float
    ack_ts: float
    raw_response: Optional[Dict[str, Any]] = None

class ExecutionFill(BaseModel):
    """
    Confirmed execution details.
    """
    execution_id: str
    order_id: str
    fill_price: float
    fill_qty: float
    fees: float = 0.0
    slippage_bps: float = 0.0
    execution_ts: float
