"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Connects to Alpaca's news WebSocket and forwards normalized live articles to the ingester.
- Reports auth, connection-limit, and disconnect states for provider health visibility.
"""

import asyncio, json, time, logging
import websockets
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("AlpacaNewsProvider")

class AlpacaNewsProvider:
    """
    Lightweight Alpaca News WebSocket client used by the news ingestion service.

    The provider calls back into NewsIngester for sentiment/event processing and
    sends status updates so the dashboard can distinguish live and disconnected states.
    """
    def __init__(self, callback, status_callback=None):
        self.api_key = settings.ALPACA_API_KEY
        self.secret_key = settings.ALPACA_SECRET_KEY
        self.callback = callback
        self.status_callback = status_callback
        self.is_running = True
        self.url = "wss://stream.data.alpaca.markets/v1beta1/news"

    async def start(self):
        """
        Maintain the Alpaca News WebSocket subscription with bounded reconnect backoff.

        Authentication uses configured environment values at runtime only; keys are
        never written to logs or proof artifacts.
        """
        if not self.api_key or self.api_key == "":
            logger.warning("Alpaca API key missing. Skipping News WebSocket.")
            return

        logger.info("Starting Alpaca News WebSocket...")
        
        backoff = 10
        while self.is_running:
            try:
                # Ping and open timeouts help classify unstable network sessions.
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=10, open_timeout=30) as ws:
                    # Expect a provider welcome/error message before auth.
                    try:
                        msg_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        msg = json.loads(msg_raw)
                        logger.info(f"Alpaca News Connect: {msg}")
                        
                        # 406 means a provider connection limit, not a bad secret.
                        if isinstance(msg, list) and msg[0].get("T") == "error":
                            err_code = msg[0].get("code")
                            if err_code == 406:
                                logger.error("Alpaca News: Connection limit exceeded (406). Applying long backoff.")
                                backoff = 120 # Wait 2 mins for Alpaca to clear the zombie session
                                break # Exit 'async with' to wait and retry
                    except asyncio.TimeoutError:
                        logger.warning("Alpaca News: Timeout waiting for welcome message.")
                        break

                    # Authenticate at runtime; credentials are not logged directly.
                    auth_msg = {
                        "action": "auth",
                        "key": self.api_key,
                        "secret": self.secret_key
                    }
                    await ws.send(json.dumps(auth_msg))
                    
                    # Treat auth failure as provider health state for the admin API.
                    auth_res_raw = await ws.recv()
                    auth_res = json.loads(auth_res_raw)
                    logger.info(f"Alpaca News Auth: {auth_res}")

                    if isinstance(auth_res, list) and auth_res[0].get("msg") != "authenticated":
                        logger.error(f"Alpaca News Auth Failed: {auth_res}")
                        if self.status_callback:
                            await self.status_callback("alpaca_news", "AUTH_FAILED", str(auth_res))
                        backoff = 60
                        break

                    # Subscribe to all available news after successful auth.
                    sub_msg = {
                        "action": "subscribe",
                        "news": ["*"]
                    }
                    await ws.send(json.dumps(sub_msg))
                    if self.status_callback:
                        await self.status_callback("alpaca_news", "CONNECTED")
                    
                    backoff = 10 # Reset backoff on success

                    async for message in ws:
                        data_list = json.loads(message)
                        for item in data_list:
                            if item.get("T") == "n": # News
                                await self.callback({
                                    "title": item.get("headline"),
                                    "url": item.get("url"),
                                    "summary": item.get("summary"),
                                    "provider": "ALPACA",
                                    "source_ts": self._parse_iso(item.get("updated_at")),
                                    "raw": item
                                })
                            elif item.get("T") == "error":
                                logger.error(f"Alpaca News Protocol Error: {item.get('msg')} (code: {item.get('code')})")
                                if item.get("code") == 406:
                                    backoff = 120
                                    raise Exception("Connection limit exceeded")
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"Alpaca News WebSocket closed: {e}. Reconnecting...")
                if self.status_callback:
                    await self.status_callback("alpaca_news", "DISCONNECTED", str(e))
            except Exception as e:
                logger.error(f"Alpaca News WebSocket error: {e}")
                if self.status_callback:
                    await self.status_callback("alpaca_news", "DISCONNECTED", str(e))
            
            if self.is_running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300)


    def _parse_iso(self, iso_str):
        """
        Parse Alpaca ISO timestamps to epoch seconds for freshness labeling.

        Falls back to current time when the provider omits or malforms the
        timestamp so ingestion can still process the article conservatively.
        """
        if not iso_str: return time.time()
        try:
            from datetime import datetime
            return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp()
        except:
            return time.time()
