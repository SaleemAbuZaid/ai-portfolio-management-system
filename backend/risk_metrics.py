"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Contains risk metric helpers used for portfolio analytics.
"""
import pandas as pd
import numpy as np

def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    if returns.empty or returns.std() == 0: return 0.0
    return (returns.mean() - risk_free_rate) / returns.std() * np.sqrt(252)

def calculate_max_drawdown(prices: pd.Series) -> float:
    if prices.empty: return 0.0
    rolling_max = prices.cummax()
    drawdown = (prices - rolling_max) / rolling_max
    return abs(float(drawdown.min()))

def calculate_volatility(returns: pd.Series) -> float:
    if returns.empty: return 0.0
    return float(returns.std() * np.sqrt(252))
