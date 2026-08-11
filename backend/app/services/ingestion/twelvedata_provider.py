"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Wraps TwelveData WebSocket/REST access for market price ingestion.
"""
import asyncio, json, time, logging, ssl
import websockets
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("TwelveDataProvider")

class TwelveDataProvider:
    """
    Stream supported market symbols from TwelveData into the market ingester.

    The provider emits both price ticks and heartbeat callbacks so the rest of
    the system can label data as live, delayed, rate-limited, or disconnected.
    """
    def __init__(self, callback):
        self.api_key = settings.TWELVEDATA_API_KEY
        self.callback = callback
        self.is_running = True
        self.url = f"wss://ws.twelvedata.com/v1/quotes/price?apikey={self.api_key}"
        # TwelveData stream subscription for the configured 12-asset universe.
        self.symbols = "AAPL,TSLA,BTC/USD,ETH/USD,XAU/USD,XAG/USD,EUR/USD,GBP/USD,USD/TRY,USD/JPY,WTI/USD,BRENT/USD"

    async def start(self):
        """
        Maintain the TwelveData WebSocket subscription with reconnect backoff.

        Price messages are forwarded to the shared market callback; heartbeat
        messages update provider health without creating artificial price ticks.
        """
        if not self.api_key or self.api_key == "":
            logger.warning("Twelve Data API key missing. Skipping WebSocket.")
            return

        logger.info(f"Starting Twelve Data WebSocket for symbols: {self.symbols}")
        
        backoff = 5
        while self.is_running:
            try:
                # Ping and open timeouts help classify unstable network sessions.
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=10, open_timeout=30) as ws:
                    # Subscribe once per connection attempt.
                    subscribe_msg = {
                        "action": "subscribe",
                        "params": {
                            "symbols": self.symbols
                        }
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info("Twelve Data: Subscribed to streams.")
                    
                    backoff = 5 # Reset backoff on success

                    async for message in ws:
                        data = json.loads(message)
                        event = data.get("event")
                        if event == "price":
                            symbol = data.get("symbol")
                            price = data.get("price")
                            await self.callback(
                                symbol=symbol,
                                price=price,
                                source="twelvedata",
                                provider_ts=data.get("timestamp"),
                                raw=data
                            )
                        elif event == "heartbeat":
                            logger.debug("Twelve Data: Heartbeat received.")
                            # Heartbeat updates health without inventing a quote.
                            await self.callback(source="twelvedata", is_heartbeat=True)
                        elif data.get("status") == "error":
                            msg = data.get("message", "Unknown error")
                            logger.error(f"Twelve Data Protocol Error: {msg}")
                            if "limit" in msg.lower():
                                backoff = 60 # Long wait for rate limits
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"Twelve Data WebSocket connection closed: {e}. Reconnecting...")
            except Exception as e:
                logger.error(f"Twelve Data WebSocket error: {e}")
            
            if self.is_running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
