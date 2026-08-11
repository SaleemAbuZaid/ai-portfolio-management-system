"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Defines the broker adapter interface shared by execution integrations.
"""
from abc import ABC, abstractmethod
from app.models.schemas.execution_schemas import OrderRequest, OrderAck, ExecutionFill
from typing import List

class BaseBrokerAdapter(ABC):
    """
    Abstract interface for executing trades, getting positions, and checking account health.
    """
    
    @abstractmethod
    async def connect(self):
        """Establish connection to the broker."""
        pass
        
    @abstractmethod
    async def submit_order(self, request: OrderRequest) -> OrderAck:
        """Submit an atomic order payload."""
        pass
        
    @abstractmethod
    async def get_positions(self) -> List[dict]:
        """Fetch current portfolio holdings."""
        pass
        
    @abstractmethod
    async def get_account(self) -> dict:
        """Fetch Buying Power, Equity, Cash."""
        pass
