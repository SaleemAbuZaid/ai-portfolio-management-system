"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Ingests market prices from Binance, CoinGecko, AlphaVantage, TwelveData, and fallback feeds.
- Normalizes ticks, publishes Redis updates, persists history, and records truthful source health.
"""
import asyncio, json, time, os, ssl, logging
from datetime import datetime, timezone
import websockets, httpx
from tenacity import retry, wait_exponential, stop_after_attempt
from app.core.redis_client import redis_bus
from app.services.cache_service import performance_cache
from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.models.all_models import PriceHistory, Asset
from sqlalchemy import select
from app.services.ingestion.twelvedata_provider import TwelveDataProvider
from app.core.symbols import normalize_symbol

settings = get_settings()
logger = logging.getLogger("MarketIngester")

BINANCE_STREAMS = {
    "BTCUSDT": "btcusdt@trade",
    "ETHUSDT": "ethusdt@trade",
}

TWELVEDATA_REST_BACKFILL_SYMBOLS = (
    "AAPL",
    "TSLA",
    "ETH/USD",
    "GBP/USD",
    "USD/TRY",
    "USD/JPY",
)

HEALTH_INFERENCE_SYMBOLS = (
    "AAPL",
    "TSLA",
    "BTC/USD",
    "ETH/USD",
    "EUR/USD",
    "GBP/USD",
    "USD/TRY",
    "USD/JPY",
    "XAU/USD",
    "XAG/USD",
    "WTI",
    "BRENT",
)

def get_safe_ssl_context():
    """Create a high-compatibility SSL context for restrictive defense environments."""
    # Use PROTOCOL_TLS_CLIENT for stricter protocol negotiation
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

class MarketIngester:
    """
    Coordinate market provider polling/streaming and publish normalized price ticks.

    Provider status is intentionally explicit: the service records connected,
    delayed, rate-limited, network-restricted, or fallback states for auditability.
    """
    def __init__(self):
        self.is_running = True
        self.last_tick_time = {}
        self.last_tick_source = {}
        self.asset_map = {} # Ticker to Asset.id mapping for persistence.
        self.last_persist_time = {} # Per-ticker throttle for history writes.
        # Provider health starts disconnected until a real heartbeat or tick is observed.
        self.source_status = {
            "binance": {
                "provider": "BINANCE",
                "category": "MARKET_DATA",
                "status": "DISCONNECTED",
                "last_success_at": None,
                "last_error_code": None,
                "last_error_message_sanitized": None,
                "latency_ms": 0,
                "is_required": True,
                "notes": "Crypto price feed (Websocket)"
            },
            "coingecko": {
                "provider": "COINGECKO",
                "category": "MARKET_DATA",
                "status": "DISCONNECTED",
                "last_success_at": None,
                "last_error_code": None,
                "last_error_message_sanitized": None,
                "latency_ms": 0,
                "is_required": False,
                "notes": "Crypto price feed (Rest)"
            },
            "alphavantage": {
                "provider": "ALPHAVANTAGE",
                "category": "MARKET_DATA",
                "status": "DISCONNECTED",
                "last_success_at": None,
                "last_error_code": None,
                "last_error_message_sanitized": None,
                "latency_ms": 0,
                "is_required": False,
                "notes": "Equity and Forex feed"
            },
            "twelvedata": {
                "provider": "TWELVEDATA",
                "category": "MARKET_DATA",
                "status": "DISCONNECTED",
                "last_success_at": None,
                "last_error_code": None,
                "last_error_message_sanitized": None,
                "latency_ms": 0,
                "is_required": False,
                "notes": "Real-time stock data (Partial Coverage)"
            },
            "internal": {
                "provider": "INTERNAL",
                "category": "INTERNAL",
                "status": "INTERNAL_FALLBACK",
                "last_success_at": time.time(),
                "last_error_code": None,
                "last_error_message_sanitized": None,
                "latency_ms": 1,
                "is_required": True,
                "notes": "Fallback pricing for stability"
            }
        }

    async def load_assets(self):
        """
        Load ticker-to-asset IDs from the database for price persistence.

        The mapping lets streaming providers publish lightweight ticks while the
        persistence task can attach each price to the normalized Asset table.
        """
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Asset))
                assets = result.scalars().all()
                self.asset_map = {a.ticker: a.id for a in assets}
                logger.info(f"Loaded {len(self.asset_map)} assets for ingestion mapping.")
        except Exception as e:
            logger.error(f"Failed to load assets: {e}")

    async def _persist_tick_bg(self, symbol, tick):
        """
        Persist one normalized tick to PriceHistory in its own async session.

        The ingestion loop calls this in the background so provider streaming is
        not blocked by database write latency.
        """
        if self.asset_map.get(symbol):
            try:
                async with AsyncSessionLocal() as session:
                    row = PriceHistory(
                        asset_id=self.asset_map[symbol],
                        timestamp=datetime.fromtimestamp(tick["ingest_ts"]),
                        price=tick["price"],
                        volume=tick["volume"],
                        provider=tick["provider"],
                        provider_ts=tick["provider_ts"],
                        ingest_ts=tick["ingest_ts"],
                        lag_ms=tick["lag_ms"]
                    )
                    session.add(row)
                    await session.commit()
            except Exception as e:
                logger.error(f"Failed to persist tick for {symbol}: {e}")

    async def _has_fresh_live_tick(self, symbol: str) -> bool:
        """Return True when Redis already has a fresh live tick for this asset."""
        try:
            existing_raw = await redis_bus.get(f"latest:tick:{symbol}")
            if not existing_raw:
                return False
            existing = json.loads(existing_raw)
            if existing.get("status_label") != "LIVE_PROVIDER":
                return False
            provider_ts = float(existing.get("provider_ts") or existing.get("ingest_ts") or 0.0)
            if provider_ts > 10000000000:
                provider_ts = provider_ts / 1000.0
            return provider_ts > 0 and (time.time() - provider_ts) <= 300
        except Exception:
            return False

    async def publish_tick(self, symbol=None, price=None, bid=None, ask=None, volume=None, sequence_ref=None, source=None, provider_ts=None, raw=None, is_heartbeat=False):
        """
        Normalize one provider tick, label its provenance, publish it to Redis, and persist history.

        LIVE_PROVIDER, DELAYED_PROVIDER, and INTERNAL_FALLBACK labels are assigned
        from the source and timestamp so the frontend can display market truth status.
        """
        if is_heartbeat and source:
            if source in self.source_status:
                self.source_status[source]["last_success_at"] = time.time()
                self.source_status[source]["status"] = "CONNECTED"
                self.source_status[source]["last_error_message_sanitized"] = None
                await self._sync_health_to_redis()
            return

        if symbol is None or price is None:
            logger.warning(f"publish_tick called with missing data for source {source}")
            return

        symbol = normalize_symbol(symbol)
        ingest_ts = time.time()
        provider_ts = provider_ts or ingest_ts
        lag_ms = max(0.0, (ingest_ts - provider_ts) * 1000.0)
        
        # Provider selection is reflected directly in provenance labels. Free or
        # rate-limited REST providers may be delayed, while the internal feed is
        # always marked as INTERNAL_FALLBACK.
        status_label = "INTERNAL_FALLBACK"
        if source == "binance":
            status_label = "LIVE_PROVIDER"
            self.source_status["binance"]["status"] = "LIVE_PROVIDER"
            self.source_status["binance"]["last_success_at"] = ingest_ts
        elif source == "coingecko":
            status_label = "DELAYED_PROVIDER"
            self.source_status["coingecko"]["status"] = "DELAYED_PROVIDER"
            self.source_status["coingecko"]["last_success_at"] = ingest_ts
        elif source == "alphavantage":
            status_label = "DELAYED_PROVIDER"
            self.source_status["alphavantage"]["status"] = "DELAYED_PROVIDER"
            self.source_status["alphavantage"]["last_success_at"] = ingest_ts
        elif source == "twelvedata":
            status_label = "LIVE_PROVIDER"
            self.source_status["twelvedata"]["status"] = "LIVE_PROVIDER"
            self.source_status["twelvedata"]["last_success_at"] = ingest_ts
        elif source == "internal":
            status_label = "INTERNAL_FALLBACK"
            self.source_status["internal"]["status"] = "INTERNAL_FALLBACK"
            self.source_status["internal"]["last_success_at"] = ingest_ts

        tick = {
            "symbol": symbol,
            "provider": f"{source}",
            "provider_ts": provider_ts,
            "ingest_ts": ingest_ts,
            "lag_ms": lag_ms,
            "price": float(price),
            "bid": float(bid) if bid is not None else None,
            "ask": float(ask) if ask is not None else None,
            "volume": float(volume) if volume is not None else None,
            "sequence_ref": str(sequence_ref) if sequence_ref is not None else None,
            "raw_payload": raw or {},
            "asset_class": "crypto" if "USDT" in symbol else "equity",
            "status_label": status_label
        }
        
        # Log provider, label, and lag so source issues can be audited later.
        source_name = str(source).upper() if source else "UNKNOWN"
        logger.info(f"[INGEST][{status_label}][{source_name}] {symbol} @ {price} (lag: {lag_ms:.2f}ms)")
    
        if source:
            if source not in self.source_status:
                self.source_status[source] = {"last_ingest_ts": 0.0, "count": 0}
                
            self.source_status[source]["last_ingest_ts"] = ingest_ts
            self.source_status[source]["stale"] = False

        if status_label != "LIVE_PROVIDER" and await self._has_fresh_live_tick(symbol):
            logger.info(
                "[INGEST][PRIORITY] Preserving fresh LIVE_PROVIDER tick for %s; skipped %s update from %s.",
                symbol,
                status_label,
                source_name,
            )
            await self._sync_health_to_redis()
            return

        # Persist history on a per-asset throttle so charts have evidence without
        # overwhelming SQLite/PostgreSQL during rapid provider updates.
        last_save = self.last_persist_time.get(symbol, 0)
        if (ingest_ts - last_save) > 45:
            self.last_persist_time[symbol] = ingest_ts
            asyncio.create_task(self._persist_tick_bg(symbol, tick))

        self.last_tick_time[symbol] = ingest_ts
        self.last_tick_source[symbol] = source
        # Redis carries the latest normalized tick for dashboard/API reads.
        await redis_bus.set(f"latest:tick:{symbol}", json.dumps(tick), ex=3600)
        await redis_bus.set(f"tick:{symbol}", json.dumps(tick), ex=3600) # Backup key
        
        # Sync health to Redis so API workers can report provider state even
        # when they are not the process running ingestion.
        await self._sync_health_to_redis()

    @retry(wait=wait_exponential(min=5, max=60), stop=stop_after_attempt(9999))
    async def _managed_crypto_stream(self):
        """Binance Hot Path: @trade stream. Fields: p=price, q=volume, t=trade_id"""
        uri = f"{settings.BINANCE_WSS_URL}?streams=" + "/".join(BINANCE_STREAMS.values())
        
        # Ultra-compatible context for restricted environments
        ssl_ctx = get_safe_ssl_context()
        
        
        try:
            async with websockets.connect(uri, ssl=ssl_ctx, ping_interval=20, ping_timeout=60) as ws:
                logger.info("[BINANCE] WebSocket Link Established.")
                self.source_status["binance"]["status"] = "CONNECTED"
                async for msg in ws:
                    envelope = json.loads(msg)
                    data = envelope.get("data", {})
                    await self.publish_tick(
                        symbol=data.get("s"), 
                        price=data.get("p"), 
                        volume=data.get("q"), 
                        sequence_ref=data.get("t"),
                        bid=None,
                        ask=None,
                        source="binance", 
                        provider_ts=data.get("E", 0) / 1000.0, 
                        raw=data
                    )
        except Exception as e:
            self.source_status["binance"]["last_error_message_sanitized"] = str(e)[:100]
            err_text = str(e).lower()
            if "wrong_version_number" in err_text or "ssl" in err_text or "record layer failure" in err_text or "reset" in err_text:
                self.source_status["binance"]["status"] = "NETWORK_RESTRICTED"
                logger.warning("[BINANCE] Network Restriction Detected (Internal Wall). Feed: PASSIVE.")
            else:
                self.source_status["binance"]["status"] = "DISCONNECTED"
                logger.error(f"[BINANCE] Connection Failure: {e}")
            await self._sync_health_to_redis()
            raise e

    async def stream_coingecko_enrichment(self):
        api_key = settings.COINGECKO_API_KEY
        # CoinGecko keys for this integration use the x-cg-internal-api-key header.
        headers = {"x-cg-internal-api-key": api_key} if api_key else {}
        base_url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": "bitcoin,ethereum", "vs_currencies": "usd", "include_last_updated_at": "true"}
        
        while self.is_running:
            start_time = time.perf_counter()
            try:
                transport = httpx.AsyncHTTPTransport(proxy=None, verify=False)
                async with httpx.AsyncClient(timeout=10, transport=transport, trust_env=False) as client:
                    r = await client.get(base_url, params=params, headers=headers)
                    self.source_status["coingecko"]["latency_ms"] = int((time.perf_counter() - start_time) * 1000)
                    if r.status_code == 200:
                        self.source_status["coingecko"]["status"] = "CONNECTED"
                        self.source_status["coingecko"]["last_success_at"] = time.time()
                        data = r.json()
                        for cid, item in data.items():
                            await self.publish_tick(
                                "BTCUSDT" if cid=="bitcoin" else "ETHUSDT",
                                price=item.get("usd"),
                                source="coingecko",
                                provider_ts=float(item.get("last_updated_at", time.time())),
                                raw=item
                            )
                    else:
                        if r.status_code in [401, 403]:
                            self.source_status["coingecko"]["status"] = "AUTH_FAILED"
                        else:
                            self.source_status["coingecko"]["status"] = "DISCONNECTED"
                        self.source_status["coingecko"]["last_error_code"] = r.status_code
            except Exception as e:
                self.source_status["coingecko"]["status"] = "NETWORK_RESTRICTED"
                self.source_status["coingecko"]["last_error_message_sanitized"] = str(e)[:100]
                if "WRONG_VERSION_NUMBER" in str(e):
                    logger.warning("[COINGECKO] Primary Link Blocked (Internal Wall). Switching to Passive Mode.")
                else:
                    logger.warning(f"[COINGECKO] Polled Enrichment Error: {e}")
            await asyncio.sleep(120)

    async def poll_alphavantage_enrichment(self):
        if not settings.ALPHAVANTAGE_API_KEY: return
        while self.is_running:
            
            async def fetch_stock(sym):
                try:
                    params = {"function": "GLOBAL_QUOTE", "symbol": sym, "apikey": settings.ALPHAVANTAGE_API_KEY}
                    transport = httpx.AsyncHTTPTransport(proxy=None, verify=False)
                    async with httpx.AsyncClient(timeout=10, transport=transport, trust_env=False) as client:
                        r = await client.get("https://www.alphavantage.co/query", params=params)
                        data = r.json()
                        
                        # AlphaVantage reports free-tier throttling inside the
                        # JSON body as "Note" or "Information" instead of only
                        # relying on HTTP 429.
                        if "Note" in data or "Information" in data:
                            logger.warning(f"[ALPHAVANTAGE] Rate Limit / Info Message: {data.get('Note') or data.get('Information')}")
                            self.source_status["alphavantage"]["status"] = "RATE_LIMITED"
                            self.source_status["alphavantage"]["last_error_code"] = 429
                            self.source_status["alphavantage"]["last_error_message_sanitized"] = str(data.get("Note") or data.get("Information"))[:100]
                            return

                        quote = data.get("Global Quote", {})
                        if quote and quote.get("05. price"):
                            await self.publish_tick(sym, price=quote.get("05. price"), source="alphavantage", raw=quote)
                        else:
                            logger.debug(f"[ALPHAVANTAGE] No quote for {sym}: {data}")
                except Exception as e:
                    logger.warning(f"[ALPHAVANTAGE][STOCKS] Error: {e}")

            async def fetch_fx(pair):
                try:
                    from_curr, to_curr = pair
                    symbol = f"{from_curr}{to_curr}"
                    params = {
                        "function": "CURRENCY_EXCHANGE_RATE", 
                        "from_currency": from_curr, 
                        "to_currency": to_curr, 
                        "apikey": settings.ALPHAVANTAGE_API_KEY
                    }
                    transport = httpx.AsyncHTTPTransport(proxy=None, verify=False)
                    async with httpx.AsyncClient(timeout=10, transport=transport, trust_env=False) as client:
                        r = await client.get("https://www.alphavantage.co/query", params=params)
                        data = r.json()

                        # AlphaVantage FX responses use the same body-level
                        # throttling fields as equity quote responses.
                        if "Note" in data or "Information" in data:
                            self.source_status["alphavantage"]["status"] = "RATE_LIMITED"
                            self.source_status["alphavantage"]["last_error_code"] = 429
                            return

                        rate_data = data.get("Realtime Currency Exchange Rate", {})
                        if rate_data and rate_data.get("5. Exchange Rate"):
                            price = rate_data.get("5. Exchange Rate")
                            await self.publish_tick(symbol, price=price, source="alphavantage", raw=rate_data)
                except Exception as e:
                    logger.warning(f"[ALPHAVANTAGE][FX] Error: {e}")

            tasks = [
                fetch_stock("AAPL"), 
                fetch_stock("TSLA"),
                fetch_fx(("EUR", "USD")), 
                fetch_fx(("GBP", "USD")),
                fetch_fx(("USD", "TRY")),
                fetch_fx(("USD", "JPY")),
                fetch_fx(("XAU", "USD")),
                fetch_fx(("XAG", "USD"))
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(300) # Full cycle cooldown

    async def poll_twelvedata_rest_backfill(self):
        """
        Backfill stale-but-supported symbols from TwelveData's 1-minute UTC time-series.

        This is deliberately conservative to avoid API credit exhaustion and to keep
        source labels based on provider timestamps, not local ingestion time.
        """
        if not settings.TWELVEDATA_API_KEY:
            return

        transport = httpx.AsyncHTTPTransport(proxy=None, verify=False)
        async with httpx.AsyncClient(timeout=12, transport=transport, trust_env=False) as client:
            while self.is_running:
                for symbol in TWELVEDATA_REST_BACKFILL_SYMBOLS:
                    if not self.is_running:
                        break

                    # Let recent TwelveData ticks win. Delayed providers should not block
                    # a fresher TwelveData refresh for the same asset.
                    if (
                        self.last_tick_source.get(symbol) == "twelvedata"
                        and time.time() - self.last_tick_time.get(symbol, 0) < 45
                    ):
                        continue

                    try:
                        params = {
                            "symbol": symbol,
                            "interval": "1min",
                            "outputsize": 1,
                            "timezone": "UTC",
                            "apikey": settings.TWELVEDATA_API_KEY,
                        }
                        started = time.perf_counter()
                        response = await client.get(
                            "https://api.twelvedata.com/time_series",
                            params=params,
                        )
                        self.source_status["twelvedata"]["latency_ms"] = int((time.perf_counter() - started) * 1000)
                        data = response.json()

                        if response.status_code == 429 or data.get("code") == 429:
                            self.source_status["twelvedata"]["status"] = "RATE_LIMITED"
                            self.source_status["twelvedata"]["last_error_code"] = 429
                            self.source_status["twelvedata"]["last_error_message_sanitized"] = str(data.get("message", "TwelveData rate limited"))[:100]
                            await self._sync_health_to_redis()
                            break

                        if data.get("status") != "ok" or not data.get("values"):
                            message = str(data.get("message", f"No TwelveData REST value for {symbol}"))
                            logger.debug("[TWELVEDATA][REST] %s: %s", symbol, message[:120])
                            continue

                        latest = data["values"][0]
                        price = latest.get("close")
                        dt_raw = latest.get("datetime")
                        if not price or not dt_raw:
                            continue

                        provider_dt = datetime.strptime(dt_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        await self.publish_tick(
                            symbol=symbol,
                            price=price,
                            source="twelvedata",
                            provider_ts=provider_dt.timestamp(),
                            raw={
                                "provider_path": "twelvedata_time_series_1min",
                                "provider_datetime_utc": dt_raw,
                                "meta": data.get("meta", {}),
                            },
                        )
                    except Exception as e:
                        self.source_status["twelvedata"]["last_error_message_sanitized"] = str(e)[:100]
                        logger.warning("[TWELVEDATA][REST] Backfill error for %s: %s", symbol, e)

                    await asyncio.sleep(1.0)

                await asyncio.sleep(75)

    async def _internal_feed_generator(self):
        """
        Generate internal fallback prices when live verification mode is off.

        These ticks keep demos responsive during provider outages, but they are
        always labeled INTERNAL_FALLBACK and never treated as external data.
        """
        if settings.LIVE_VERIFY_MODE:
            logger.info("[MARKET] LIVE_VERIFY_MODE active: Internal generator DISABLED.")
            return

        import random
        # Baseline prices (12 assets)
        base_prices = {
            "AAPL": 230.20,
            "TSLA": 180.50,
            "BTC/USD": 74000.0,
            "ETH/USD": 2250.0,
            "XAU/USD": 2350.0,
            "XAG/USD": 28.50,
            "EUR/USD": 1.0850,
            "GBP/USD": 1.2650,
            "USD/TRY": 32.50,
            "USD/JPY": 155.20,
            "WTI": 82.30,
            "BRENT": 86.40
        }
        current_prices = base_prices.copy()

        while self.is_running:
            await asyncio.sleep(1.5) # High-frequency feel
            for asset in base_prices.keys():
                # Only generate data if real data hasn't arrived in 10s
                if time.time() - self.last_tick_time.get(asset, 0) > 10:
                    # Small random-walk movement keeps fallback charts readable
                    # without pretending to be provider-sourced market data.
                    change_pct = random.gauss(0, 0.0002) 
                    current_prices[asset] *= (1 + change_pct)
                    
                    await self.publish_tick(
                        symbol=asset, 
                        price=round(current_prices[asset], 4), 
                        source="internal",
                        volume=random.randint(100, 500) / 10.0
                    )

    async def run(self):
        logger.info(f"Market Ingest Engine Starting (Mode: {'LIVE_VERIFY' if settings.LIVE_VERIFY_MODE else 'NORMAL'})...")
        await redis_bus.connect()
        await self.load_assets() # Asset IDs are needed before persistence can run.
        
        tasks = []
        if settings.LIVE_VERIFY_MODE or settings.ENABLE_LIVE_MARKET_DATA:
            tasks.append(self._managed_crypto_stream())
            
        if settings.LIVE_VERIFY_MODE or settings.ENABLE_ENRICHMENT:
            tasks.append(self.stream_coingecko_enrichment())
            tasks.append(self.poll_alphavantage_enrichment())
            
        if not settings.LIVE_VERIFY_MODE:
            tasks.append(self._internal_feed_generator())
        
        if settings.LIVE_VERIFY_MODE or settings.ENABLE_LIVE_MARKET_DATA:
            td_provider = TwelveDataProvider(self.publish_tick)
            tasks.append(td_provider.start())
            tasks.append(self.poll_twelvedata_rest_backfill())
            
        tasks.append(self._periodic_health_check())

        await asyncio.gather(*tasks, return_exceptions=True)

    async def start_streaming(self):
        """Alias for run() to match API control naming."""
        await self.run()

    def stop(self):
        """Graceful shutdown flag."""
        self.is_running = False
        logger.info("Market Ingest Engine shutdown requested.")

    async def _infer_source_health_from_cache(self):
        """
        API workers may not own the ingestion loop. Infer provider health from
        Redis tick cache so the dashboard reflects the active data plane.
        """
        now = time.time()

        try:
            await redis_bus.connect()
        except Exception:
            return

        for symbol in HEALTH_INFERENCE_SYMBOLS:
            try:
                raw = await redis_bus.get(f"latest:tick:{symbol}")
                if not raw:
                    continue

                tick = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
                provider = str(tick.get("provider") or "").strip().lower()
                if not provider:
                    continue

                if "twelvedata" in provider:
                    provider_key = "twelvedata"
                elif "binance" in provider:
                    provider_key = "binance"
                elif "coingecko" in provider:
                    provider_key = "coingecko"
                elif "alphavantage" in provider:
                    provider_key = "alphavantage"
                elif "internal" in provider or "fallback" in provider:
                    provider_key = "internal"
                else:
                    continue

                if provider_key not in self.source_status:
                    continue

                ingest_ts = float(tick.get("ingest_ts") or 0.0)
                provider_ts = float(tick.get("provider_ts") or ingest_ts or 0.0)
                if provider_ts > 10_000_000_000:
                    provider_ts = provider_ts / 1000.0

                if ingest_ts <= 0 or now - ingest_ts > 1800:
                    continue

                status_label = str(tick.get("status_label") or "").upper()
                if status_label not in {"LIVE_PROVIDER", "DELAYED_PROVIDER", "INTERNAL_FALLBACK"}:
                    status_label = "DELAYED_PROVIDER" if provider_key != "internal" else "INTERNAL_FALLBACK"

                current_last = float(self.source_status[provider_key].get("last_success_at") or 0.0)
                if ingest_ts >= current_last:
                    self.source_status[provider_key]["status"] = status_label
                    self.source_status[provider_key]["last_success_at"] = ingest_ts
                    self.source_status[provider_key]["last_ingest_ts"] = ingest_ts
                    self.source_status[provider_key]["latency_ms"] = int(float(tick.get("lag_ms") or 0))
                    self.source_status[provider_key]["last_error_code"] = None
                    self.source_status[provider_key]["last_error_message_sanitized"] = None
            except Exception:
                continue

    async def get_source_health(self):
        """
        Return standardized market provider health for API/admin endpoints.

        Health rows distinguish connected, delayed, stale, rate-limited, and
        internal fallback states so provenance is visible to the dashboard.
        """
        await self._infer_source_health_from_cache()
        now = time.time()
        health = {}
        for src, status in self.source_status.items():
            last_ts = float(status.get("last_success_at", 0.0) or 0.0)
            
            # Determine last_ingest_ts for legacy compatibility
            try:
                last_ingest_ts = float(status.get("last_ingest_ts") or 0.0)
            except (ValueError, TypeError):
                last_ingest_ts = 0.0
            if last_ingest_ts == 0.0 and last_ts > 0.0:
                last_ingest_ts = last_ts

            # A provider must have a recent success heartbeat to remain connected.
            is_stale = not (last_ts > 0 and (now - last_ts) < 600)
            st = status.get("status", "DISCONNECTED")
            
            # If explicit error status from provider, keep it
            if status.get("last_error_code") in [401, 403]:
                st = "AUTH_FAILED"
            elif status.get("last_error_code") == 429:
                st = "RATE_LIMITED"

            # Only external LIVE_PROVIDER or DELAYED_PROVIDER rows can be
            # connected; stale/error/internal rows remain visible but disconnected.
            external_live_statuses = ["CONNECTED", "LIVE_PROVIDER", "DELAYED_PROVIDER"]
            connected = (st in external_live_statuses) and (not is_stale)
            
            # Internal fallback may be available but is not an external connection.
            if st == "INTERNAL_FALLBACK" or src == "internal":
                st = "INTERNAL_FALLBACK"
                connected = False # Internal data is not provider connectivity.
                is_stale = False # Fallback availability is not an external outage.
                reliability = "FALLBACK"
            else:
                # Reliability summarizes provider health for the admin table.
                if st in ["AUTH_FAILED", "RATE_LIMITED", "NETWORK_RESTRICTED", "ERROR"]:
                    reliability = "ERROR"
                    connected = False # Error/rate-limited providers are not connected.
                elif is_stale:
                    reliability = "STALE"
                    st = "DISCONNECTED" # Stale providers should not look live.
                    connected = False
                else:
                    reliability = "HEALTHY"

            health[src] = {
                "provider": status.get("provider", src.upper()),
                "category": status.get("category", "MARKET_DATA"),
                "status": st,
                "last_success_at": last_ts,
                "last_error_code": status.get("last_error_code"),
                "last_error_message_sanitized": status.get("last_error_message_sanitized"),
                "latency_ms": status.get("latency_ms", 0),
                "is_required": status.get("is_required", False),
                "notes": status.get("notes", ""),
                "stale": is_stale,
                "label": st,
                "connected": connected,
                "reliability": reliability,
                "last_ingest_ts": last_ingest_ts
            }

        return health

    async def _sync_health_to_redis(self):
        """Pushes local source status to Redis for cross-worker visibility."""
        try:
            health = await self.get_source_health()
            if health:
                await redis_bus.set("market:source_health", json.dumps(health), ex=300)
        except Exception as e:
            logger.error(f"Failed to sync health to Redis: {e}")

    async def _periodic_health_check(self):
        """Ensures health status is synced even if no ticks are flowing."""
        while self.is_running:
            await self._sync_health_to_redis()
            await asyncio.sleep(10)

market_ingester = MarketIngester()

if __name__ == "__main__":
    # Setup basic logging to see the verification output
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    asyncio.run(market_ingester.run())
