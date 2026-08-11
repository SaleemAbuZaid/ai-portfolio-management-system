"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Legacy market worker entry point kept for ingestion compatibility checks.
"""
import asyncio
import websockets
import json
from datetime import datetime, timezone
import logging
import ssl

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

async def binance_market_ingestor(redis_client, stream_name: str = "stream:market_ticks"):
    """
    Subscribes to Binance WebSocket and streams raw ticks to Redis avoiding python blocking.
    """
    # Using combined stream format for future-proofing and consistency
    url = f"{settings.BINANCE_WSS_URL}?streams=btcusdt@trade"
    
    while True:
        try:
            # Ultra-compatible context for blocked verification environments
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

            async with websockets.connect(url, ssl=ssl_ctx, ping_interval=10, ping_timeout=5) as ws:
                logger.info(f"Connected to {url}")
                async for msg in ws:
                    envelope = json.loads(msg)
                    # If using /stream?streams=..., Binance wraps in {"stream": "...", "data": {...}}
                    data = envelope.get("data", envelope)
                    # Normalizing to strict Schema
                    normalized = {
                        "provider": "binance",
                        "asset_id": "BTC/USDT",
                        "provider_ts": data.get("E", int(datetime.now(timezone.utc).timestamp() * 1000)),
                        "ingest_ts": int(datetime.now(timezone.utc).timestamp() * 1000),
                        "price": float(data.get("p", 0.0)),
                        "volume": float(data.get("q", 0.0))
                    }
                    await redis_client.xadd(stream_name, {"payload": json.dumps(normalized)}, maxlen=10000)
                    logger.debug(f"Pushed tick to {stream_name}")
        except Exception as e:
            logger.warning(f"WebSocket closed or error: {e}. Reconnecting in 2s...")
            await asyncio.sleep(2)

if __name__ == "__main__":
    # Placeholder for standalone worker testing
    pass
