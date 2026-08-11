"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Provides paper-execution support for local testing and broker-proof workflows.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
import aiohttp
from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class AbstractBroker:
    async def submit_order(self, intent_hash, symbol, side):
        raise NotImplementedError

class PaperBrokerAdapter(AbstractBroker):
    def __init__(self):
        self.headers = {
            "APCA-API-KEY-ID": settings.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": settings.ALPACA_SECRET_KEY
        }
        self.base_url = settings.ALPACA_URL
        
    async def submit_order(self, intent_hash, symbol, side):
        if settings.TRADING_MODE != "PAPER":
            logger.warning("Live Execution attempted but disabled. Dropping order.")
            return {"status": "REJECTED_POLICY"}
            
        url = f"{self.base_url}/v2/orders"
        payload = {
            "symbol": symbol,
            "qty": 1,
            "side": side.lower(),
            "type": "market",
            "time_in_force": "day",
            "client_order_id": intent_hash
        }
        
        # Async HTTP Request executing real paper trade
        if self.headers.get("APCA-API-KEY-ID") and self.headers.get("APCA-API-KEY-ID") != "YOUR_ALPACA_KEY":
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=self.headers) as resp:
                        if resp.status == 403:
                            logger.error(f"ALPACA FORBIDDEN (403): Check API Keys and Paper URL. Response: {await resp.text()}")
                            return {"id": intent_hash, "status": "AUTH_FAILED_403"}
                        
                        resp_data = await resp.json()
                        logger.info(f"REAL PAPER EXECUTION ({resp.status}): {resp_data}")
                        return {
                            "id": intent_hash,
                            "status": resp_data.get("status", "unknown"),
                            "filled_qty": resp_data.get("filled_qty", "0"),
                            "filled_avg_price": resp_data.get("filled_avg_price", "0.0"),
                            "request_ts": int(datetime.now(timezone.utc).timestamp() * 1000)
                        }
            except Exception as e:
                logger.error(f"Alpaca API connection failed: {e}")
                
        # Virtual execution for testing framework logic without active keys
        await asyncio.sleep(0.05)
        logger.info(f"VIRTUAL PAPER EXECUTION: {side} 1 {symbol}")
        return {
            "id": intent_hash,
            "status": "filled_virtual",
            "filled_qty": "1",
            "filled_avg_price": "0.00", # Price fetched by ledger reconciliation usually
            "request_ts": int(datetime.now(timezone.utc).timestamp() * 1000)
        }
async def execution_loop(redis_client):
    """
    Consumer Group loop picking up `signal_events` and routing to broker.
    """
    broker = PaperBrokerAdapter()
    last_id = "0-0"
    
    while True:
        try:
            messages = await redis_client.xread({"stream:signal_events": last_id}, count=1, block=1000)
            if not messages:
                continue
                
            for stream, entries in messages:
                for message_id, msg in entries:
                    raw_signal = json.loads(msg[b"payload"].decode('utf-8'))
                    
                    # 1. Stale Guard Check
                    current_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    if (current_ms - raw_signal.get("signal_ts", current_ms)) > 2000:
                        logger.warning(f"Drop {raw_signal['signal_id']} - STALE")
                        last_id = message_id
                        continue
                        
                    # 2. Execute
                    resp = await broker.submit_order(
                        intent_hash=raw_signal["signal_id"],
                        symbol=raw_signal["asset_id"],
                        side=raw_signal["decision"]
                    )
                    
                    # 3. CDC Outbox (Send to postgres)
                    await redis_client.lpush("ledger_outbox", json.dumps(resp))
                    last_id = message_id
                    
        except Exception as e:
            logger.error(f"Execution Router Exception: {e}")
            await asyncio.sleep(1)
