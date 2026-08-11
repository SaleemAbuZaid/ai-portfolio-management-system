"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Exposes broker status, orders, and positions for the Alpaca Paper dashboard panel.
- Masks account identifiers and keeps execution telemetry separate from credentials.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from app.services.broker.alpaca_adapter import alpaca_adapter
from app.core.config import get_settings
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
from app.api.v1.auth import check_role

router = APIRouter()
settings = get_settings()

@router.get("/status", dependencies=[Depends(check_role(["BROKER", "ADMIN"]))])
async def get_broker_status():
    """
    Return broker account status for the Broker Panel.

    Alpaca account numbers are masked, while cash, buying power, and AUM remain
    visible for paper-trading proof and dashboard review.
    """
    if settings.TRADING_MODE != "PAPER":
        return {
            "status": "STUB_MODE",
            "provider": "SIMULATION",
            "cash": 100000.0,
            "portfolio_value": 100000.0,
            "buying_power": 400000.0,
            "currency": "USD"
        }
    
    try:
        account = await alpaca_adapter.get_account()
        account_num = account.get("account_number", "********")
        masked_account = f"********{account_num[-4:]}" if len(account_num) >= 4 else "********"
        
        return {
            "provider": "Alpaca Paper",
            "account_status": account.get("status", "UNKNOWN"),
            "cash": float(account.get("cash", 0.0)),
            "portfolio_value": float(account.get("portfolio_value", 0.0)),
            "buying_power": float(account.get("buying_power", 0.0)),
            "currency": account.get("currency", "USD"),
            "trading_blocked": account.get("trading_blocked", False),
            "transfers_blocked": account.get("transfers_blocked", False),
            "account_number": masked_account,
            "account_number_masked": masked_account,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Broker Status Error: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch broker status: {str(e)}")

@router.get("/orders", dependencies=[Depends(check_role(["BROKER", "ADMIN"]))])
async def get_broker_orders(limit: int = 20):
    """
    Return recent Alpaca Paper orders for the Broker Panel.

    The data is provider metadata only and is used to show paper execution
    history without exposing credentials.
    """
    try:
        orders = await alpaca_adapter.get_orders(status="all", limit=limit)
        return orders
    except Exception as e:
        logger.error(f"Broker Orders Error: {e}")
        return []

@router.get("/positions", dependencies=[Depends(check_role(["BROKER", "ADMIN"]))])
async def get_broker_positions():
    """
    Return current Alpaca Paper positions for exposure review.

    Positions are shown separately from model portfolio holdings so users can
    distinguish external paper brokerage state from local allocation demos.
    """
    try:
        positions = await alpaca_adapter.get_positions()
        return positions
    except Exception as e:
        logger.error(f"Broker Positions Error: {e}")
        return []
