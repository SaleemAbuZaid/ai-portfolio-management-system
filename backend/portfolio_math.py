"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Contains portfolio math helpers used by tests and allocation calculations.
"""
import pandas as pd
import numpy as np

def normalize_weights(weights: dict) -> dict:
    """Ensure weights sum to 1.0. Raises ValueError if all zero or negative weights present."""
    if not weights: return {}
    vals = list(weights.values())
    if any(v < 0 for v in vals):
        raise ValueError("Weights cannot be negative")
    total = sum(vals)
    if total == 0:
        raise ValueError("Total weight cannot be zero")
    return {k: v / total for k, v in weights.items()}

def calculate_portfolio_value(positions: dict) -> float:
    """positions: {symbol: {quantity: float, current_price: float}}"""
    return sum(pos['quantity'] * pos['current_price'] for pos in positions.values())

def generate_rebalance_trades(current_positions: dict, target_weights: dict, total_value: float) -> list:
    """
    Generates a list of trade dictionaries to align current positions with target weights.
    current_positions: {symbol: {quantity: float, current_price: float}}
    """
    trades = []
    for symbol, target_weight in target_weights.items():
        target_value = total_value * target_weight
        curr = current_positions.get(symbol, {"quantity": 0, "current_price": 0})
        curr_value = curr['quantity'] * curr['current_price']
        diff_value = target_value - curr_value
        
        if abs(diff_value) > 0.01:
            price = curr['current_price']
            if price == 0: continue
            qty = abs(diff_value) / price
            trades.append({
                "symbol": symbol,
                "action": "BUY" if diff_value > 0 else "SELL",
                "quantity": round(qty, 6),
                "price": price
            })
    return trades
