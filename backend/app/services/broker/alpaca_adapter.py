"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Wraps Alpaca Paper REST endpoints for account, order, position, and proof workflows.
- Returns provider order metadata needed for execution audit without logging credentials.
"""

import logging
import time
import httpx
from .base import BaseBrokerAdapter
from app.models.schemas.execution_schemas import OrderRequest, OrderAck
from app.core.config import get_settings

logger = logging.getLogger("AlpacaAdapter")

class AlpacaAdapter(BaseBrokerAdapter):
    """
    Paper-trading broker adapter for Alpaca's v2 REST API.

    The adapter centralizes broker requests so execution, portfolio telemetry,
    and Step 7 proof generation all use the same paper-trading integration.
    """
    def __init__(self):
        self.settings = get_settings()
        self.api_key = getattr(self.settings, 'ALPACA_API_KEY', "")
        self.secret_key = getattr(self.settings, 'ALPACA_SECRET_KEY', "")
        self.base_url = getattr(self.settings, 'ALPACA_URL', "https://paper-api.alpaca.markets")
        if not self.base_url.endswith("/v2") and not self.base_url.endswith("/v2/"):
            self.base_url = self.base_url.rstrip("/") + "/v2/"
        else:
            self.base_url = self.base_url.rstrip("/") + "/"
        
        self.headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json"
        }
        self.client = httpx.AsyncClient(headers=self.headers, base_url=self.base_url, timeout=10.0)

    async def connect(self):
        """
        Verify Alpaca Paper account connectivity for startup and health checks.

        The method logs status only; credentials remain inside configuration and
        are never returned or written to proof artifacts.
        """
        try:
            res = await self.get_account()
            if res and res.get("status") == "ACTIVE":
                logger.info("Connected to Alpaca Paper Trading successfully.")
            else:
                logger.warning("Alpaca connection succeeded but account not ACTIVE or keys invalid.")
        except Exception as e:
            logger.error(f"Alpaca connection failed: {e}")

    async def execute_order(self, symbol: str, qty: float, side: str) -> dict:
        """
        Submit a simple market order for backtest/execution integrations.

        Returns the provider order id and status when Alpaca accepts the order,
        or None when the submission is rejected.
        """
        request = OrderRequest(symbol=symbol, qty=qty, side=side.upper(), order_type="market", time_in_force="gtc")
        ack = await self.submit_order(request)
        if ack.status in ["accepted", "filled", "new"]:
            return {"id": ack.order_id, "status": ack.status}
        return None

    async def get_clock(self) -> dict:
        """Return Alpaca's US equity market clock, defaulting closed on failure."""
        try:
            res = await self.client.get("clock")
            res.raise_for_status()
            return res.json()
        except Exception as e:
            logger.error(f"Failed to fetch market clock: {e}")
            return {"is_open": False}

    async def submit_order(self, request: OrderRequest, extended_hours: bool = False) -> OrderAck:
        """
        Submit one order to Alpaca Paper and return a normalized acknowledgement.

        The acknowledgement carries the provider order id, status, timestamps,
        and raw provider response so Step 7 execution proof can verify UUIDs.
        """
        req_ts = time.time()
        payload = {
            "symbol": request.symbol,
            "qty": str(request.qty),
            "side": request.side.lower(),
            "type": request.order_type,
            "time_in_force": request.time_in_force,
            "extended_hours": extended_hours
        }
        try:
            if not self.api_key:
                logger.error("Alpaca API Key missing. Cannot submit order.")
                return OrderAck(
                    order_id="",
                    symbol=request.symbol,
                    side=request.side,
                    qty=request.qty,
                    status="failed_unauthorized",
                    request_ts=req_ts,
                    ack_ts=time.time()
                )
            
            response = await self.client.post("orders", json=payload)
            response.raise_for_status()
            data = response.json()
            
            return OrderAck(
                order_id=data.get("id"),
                symbol=request.symbol,
                side=request.side,
                qty=request.qty,
                status=data.get("status"),
                request_ts=req_ts,
                ack_ts=time.time(),
                raw_response=data
            )
        except httpx.HTTPStatusError as e:
            # Capture only sanitized provider error details for audit debugging.
            error_details = {
                "status_code": e.response.status_code,
                "reason": e.response.reason_phrase,
                "response_text_sanitized": e.response.text[:500],
                "url": str(e.request.url),
                "method": e.request.method
            }
            
            if e.response.status_code == 403:
                logger.error(f"🔴 [ALPACA][403] Authorization Forbidden. Verify ALPACA_URL (Paper vs Live) and Keys. Details: {error_details}")
            else:
                logger.error(f"🔴 [ALPACA][HTTP_ERROR] {error_details}")
            
            # Re-raise so route-level proof logic can classify the failed order.
            raise
        except Exception as e:
            logger.error(f"Failed to submit Alpaca order: {e}")
            return OrderAck(
                order_id="",
                symbol=request.symbol,
                side=request.side,
                qty=request.qty,
                status="rejected",
                request_ts=req_ts,
                ack_ts=time.time()
            )

    async def get_positions(self) -> list:
        """Return current Alpaca Paper positions, or an empty list if unavailable."""
        if not self.api_key:
            return []
            
        try:
            res = await self.client.get("positions")
            res.raise_for_status()
            return res.json()
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return []

    async def get_account(self) -> dict:
        """
        Return Alpaca Paper account metadata for portfolio/status endpoints.

        Without credentials the adapter reports an inactive internal state rather
        than pretending an external brokerage connection exists.
        """
        if not self.api_key:
            return {"status": "INACTIVE_internal", "cash": "100000.00"}
            
        try:
            res = await self.client.get("account")
            res.raise_for_status()
            return res.json()
        except Exception as e:
            logger.error(f"Failed to fetch account info: {e}")
            raise

    async def get_orders(self, limit: int = 10, status: str = "all") -> list:
        """Fetch recent Alpaca Paper orders for broker panels and UUID proof."""
        if not self.api_key:
            return []
        try:
            params = {"limit": limit, "status": status}
            res = await self.client.get("orders", params=params)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            logger.error(f"Failed to fetch orders: {e}")
            return []

    async def get_order(self, order_id: str) -> dict:
        """Fetch one Alpaca Paper order by provider UUID for fill polling."""
        if not self.api_key or not order_id:
            return {}
        try:
            res = await self.client.get(f"orders/{order_id}")
            res.raise_for_status()
            return res.json()
        except Exception as e:
            logger.error(f"Failed to fetch order {order_id}: {e}")
            return {}

alpaca_adapter = AlpacaAdapter()
