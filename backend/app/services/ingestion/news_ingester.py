"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Ingests, deduplicates, scores, and persists financial news from live and backup sources.
- Publishes sentiment/event telemetry while preserving honest provider provenance labels.
"""
import asyncio, httpx, time, hashlib, json, logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, desc
from loguru import logger

from app.core.redis_client import redis_bus
from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.models.all_models import News, Sentiment, Asset
from app.services.nlp_service import NLPService
from app.services.ai_engine.event_detector import event_detector
from app.services.ingestion.alpaca_news_provider import AlpacaNewsProvider

settings = get_settings()

MARKETAUX_POLL_SECONDS = 30
EVENT_REGISTRY_POLL_SECONDS = 60

def _provider_timestamp(value) -> float:
    """Parse provider publication timestamps for newest-first ingestion."""
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0

class NewsIngester:
    """
    Manage live news providers, backup continuity feed, NLP scoring, and persistence.

    Backup/internal articles are useful for continuity during provider outages, but
    the service marks them as fallback so the dashboard never presents them as live.
    """
    def __init__(self):
        self.is_running = True
        self.last_news_ts = 0
        self.asset_map = {} # Ticker to Asset.id mapping for sentiment linkage.
        self.nlp = None # NLPService loads lazily to keep startup lightweight.
        self.processed_ids = set() # In-memory dedup cache for the current process.
        self.source_status = {
            "alpaca_news": {
                "provider": "ALPACA_NEWS",
                "category": "NEWS",
                "status": "DISCONNECTED",
                "last_success_at": None,
                "last_error_code": None,
                "last_error_message_sanitized": None,
                "latency_ms": 0,
                "is_required": True,
                "notes": "Real-time streaming via Alpaca SDK"
            },
            "marketaux": {
                "provider": "MARKETAUX",
                "category": "NEWS",
                "status": "DISCONNECTED",
                "last_success_at": None,
                "last_error_code": None,
                "last_error_message_sanitized": None,
                "latency_ms": 0,
                "is_required": False,
                "notes": "Rest API for equity and crypto news"
            },
            "event_registry": {
                "provider": "EVENT_REGISTRY",
                "category": "NEWS",
                "status": "DISCONNECTED",
                "last_success_at": None,
                "last_error_code": None,
                "last_error_message_sanitized": None,
                "latency_ms": 0,
                "is_required": False,
                "notes": "Global institutional news provider (NewsAPI.ai)"
            },
            "backup_news": {
                "provider": "BACKUP_NEWS",
                "category": "INTERNAL",
                "status": "INTERNAL_FALLBACK",
                "last_success_at": time.time(),
                "last_error_code": None,
                "last_error_message_sanitized": None,
                "latency_ms": 1,
                "is_required": True,
                "notes": "Fallback news continuity feed"
            }
        }

    async def load_assets(self):
        """
        Fetch asset mapping from the database on startup.

        The mapping lets news headlines attach sentiment/event rows to known
        portfolio assets while general macro news remains asset-neutral.
        """
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Asset))
                assets = result.scalars().all()
                self.asset_map = {a.ticker: a.id for a in assets}
                logger.info(f"Loaded {len(self.asset_map)} assets for news mapping.")
        except Exception as e:
            logger.error(f"Failed to load assets for news: {e}")

    async def update_provider_status(self, provider_key: str, status: str, error_message: str = None):
        """Update provider heartbeat status for connection events without article payloads."""
        if provider_key not in self.source_status:
            return

        self.source_status[provider_key]["status"] = status
        if status == "CONNECTED":
            self.source_status[provider_key]["last_success_at"] = time.time()
            self.source_status[provider_key]["last_error_code"] = None
            self.source_status[provider_key]["last_error_message_sanitized"] = None
        elif error_message:
            self.source_status[provider_key]["last_error_message_sanitized"] = error_message[:100]

        await self._sync_health_to_redis()

    async def process_article(self, article: dict):
        """
        Accept one raw provider article and schedule ingestion processing.

        The function performs fast hash-based deduplication, updates provider
        heartbeat state, and offloads database/NLP work so provider polling is
        not blocked by model or database latency.
        """
        title = article.get("title", "No Title")
        url = article.get("url", "")
        article_id = hashlib.sha256(f"{title}{url}".encode()).hexdigest()
            
        # Article arrival is a provider heartbeat. Backup/internal providers are
        # marked as fallback, while external providers can become connected.
        provider_raw = str(article.get("provider", "UNKNOWN")).upper()
        # Normalize provider keys to the health table naming convention.
        provider_key = provider_raw.lower()
        if provider_raw == "ALPACA": provider_key = "alpaca_news"
        
        if provider_key in self.source_status:
            if "BACKUP" in provider_raw or "INTERNAL" in provider_raw:
                self.source_status[provider_key]["status"] = "INTERNAL_FALLBACK"
            else:
                self.source_status[provider_key]["status"] = "CONNECTED"
            self.source_status[provider_key]["last_success_at"] = time.time()
            asyncio.create_task(self._sync_health_to_redis())
            
        self.last_news_ts = int(time.time())

        if article_id in self.processed_ids:
            return

        # DB persistence and NLP scoring can be slower than provider polling.
        asyncio.create_task(self._process_article_heavy_bg(article, article_id))

    async def _process_article_heavy_bg(self, article: dict, article_id: str):
        """
        Persist and score one deduplicated article in the background.

        The pipeline checks DB deduplication, writes News/Sentiment rows, detects
        events, updates the recent-news cache, and publishes a scored payload to
        Redis for the dashboard/WebSocket stream.
        """
        if not self.asset_map:
            await self.load_assets()
            
        if not self.nlp:
            self.nlp = NLPService()

        ingest_ts = time.time()
        source_ts = article.get("source_ts") or ingest_ts
        provider = str(article.get("provider", "UNKNOWN")).upper()
        title = article.get("title", "No Title")
        url = article.get("url", "")
        
        try:
            async with AsyncSessionLocal() as session:
                # Check DB deduplication because another worker may have handled
                # the article before this process saw it.
                existing = await session.execute(select(News).where(News.article_id == article_id))
                existing_news = existing.scalar_one_or_none()
                if existing_news:
                    # A provider re-sent a known article. Keep the original
                    # DB ingest_ts as the article's first real received time;
                    # provider health already tracks the live polling heartbeat.
                    self.processed_ids.add(article_id)
                    return

                # Validation fixtures exercise recommendation logic but should
                # not pollute the persisted production news table.
                is_validation_fixture = settings.STEP12_VALIDATION_MODE and ("BULLISH fixture" in title or "BEARISH fixture" in title)
                
                pub_at = datetime.fromtimestamp(source_ts, timezone.utc)
                news_entry = News(
                    article_id=article_id,
                    provider=provider,
                    headline=title,
                    url=url,
                    published_at=pub_at,
                    ingest_ts=ingest_ts,
                    raw_payload=json.dumps(article.get("raw", {}))
                )
                
                if not is_validation_fixture:
                    session.add(news_entry)
                    await session.flush() # News.id is needed for sentiment/event rows.
                else:
                    # For validation fixtures, we skip DB persistence but continue for logic/UI
                    news_entry.id = int(-1) # type: ignore # Transient fixture ID.
                
                # Score headline plus summary so short finance headlines still
                # receive contextual sentiment when a summary is available.
                text_to_score = f"{title} {article.get('summary', '')}".strip()
                
                # Validation mode uses deterministic scores so tests do not
                # depend on NLP model load time or model nondeterminism.
                if settings.STEP12_VALIDATION_MODE and "BULLISH fixture" in title:
                    sentiment_score = 0.95
                    sentiment_label = "BULLISH_FIXTURE"
                elif settings.STEP12_VALIDATION_MODE and "BEARISH fixture" in title:
                    sentiment_score = -0.95
                    sentiment_label = "BEARISH_FIXTURE"
                else:
                    scores = self.nlp.analyze_sentiment(text_to_score)
                    sentiment_score = scores["score"]
                    sentiment_label = scores["label"]

                # Link sentiment to known assets by ticker mention; macro news
                # remains asset-neutral.
                detected_assets = []
                import re
                for ticker, asset_id in self.asset_map.items():
                    pattern = rf"\b{re.escape(ticker)}\b"
                    if re.search(pattern, title, re.IGNORECASE):
                        detected_assets.append(asset_id)
                
                detected_assets = list(set(detected_assets))
                
                if not is_validation_fixture:
                    if not detected_assets:
                        sentiment_entry = Sentiment(
                            news_id=news_entry.id,
                            asset_id=None,
                            score=sentiment_score,
                            label=sentiment_label
                        )
                        session.add(sentiment_entry)
                    else:
                        for asset_id in detected_assets:
                            sentiment_entry = Sentiment(
                                news_id=news_entry.id,
                                asset_id=asset_id,
                                score=sentiment_score,
                                label=sentiment_label
                            )
                            session.add(sentiment_entry)

                # Event detection writes macro or asset-specific events that the
                # recommender can use as a decision modifier.
                if not is_validation_fixture:
                    if not detected_assets:
                        await event_detector.detect_and_persist(news_entry, None, session) # type: ignore
                    else:
                        for asset_id in detected_assets:
                            await event_detector.detect_and_persist(news_entry, asset_id, session)

                if not is_validation_fixture:
                    await session.commit()
                else:
                    await session.rollback() # Fixture rows must not leak into DB.
                
                self.processed_ids.add(article_id)

                # Deterministic validation fixtures are stored briefly in Redis
                # so the recommender can exercise BUY/SELL paths on demand.
                if settings.STEP12_VALIDATION_MODE and "FIXTURE" in str(sentiment_label):
                    for ticker, asset_id in self.asset_map.items():
                        if asset_id in detected_assets:
                            fixture_key = f"fixture:{ticker.upper()}"
                            fixture_data = {
                                "sentiment": sentiment_score,
                                "forecast": 0.08 if "BULLISH" in str(sentiment_label) else -0.08,
                                "ts": time.time()
                            }
                            await redis_bus.set(fixture_key, json.dumps(fixture_data), ex=300)
                            logger.info(f"[VALIDATION] Injected Redis Fixture for {ticker}: {sentiment_label}")
                
                # Publish the scored article for WebSocket subscribers and UI refresh.
                scored_payload = {
                    "article_id": article_id,
                    "headline": title,
                    "url": url,
                    "provider": provider,
                    "timestamp": pub_at.isoformat(),
                    "published_at": pub_at.isoformat(),
                    "last_updated": datetime.fromtimestamp(ingest_ts, timezone.utc).isoformat(),
                    "received_at": datetime.fromtimestamp(ingest_ts, timezone.utc).isoformat(),
                    "sentiment_score": sentiment_score,
                    "sentiment_label": sentiment_label,
                    "ingest_ts": ingest_ts,
                    "tickers": [t for t, i in self.asset_map.items() if i in detected_assets]
                }
                await redis_bus.publish("news_scored", scored_payload)
                
                # Refresh the hot cache so /news/latest can serve normalized rows
                # without repeating this DB join on every dashboard poll.
                try:
                    from app.services.cache_service import performance_cache
                    
                    if is_validation_fixture:
                        # Fixtures appear in the API cache for validation but
                        # remain labeled INTERNAL_FALLBACK and are not persisted.
                        current_cache = await performance_cache.get("recent_news_cache") or []
                        fixture_entry = {
                            "id": -1,
                            "headline": title,
                            "url": url,
                            "timestamp": pub_at.isoformat(),
                            "published_at": pub_at.isoformat(),
                            "last_updated": datetime.fromtimestamp(ingest_ts, timezone.utc).isoformat(),
                            "received_at": datetime.fromtimestamp(ingest_ts, timezone.utc).isoformat(),
                            "ingest_ts": ingest_ts,
                            "sentiment": {"score": float(sentiment_score), "label": sentiment_label},
                            "asset": [t for t, i in self.asset_map.items() if i in detected_assets][0] if detected_assets else None,
                            "provider": provider,
                            "source_type": "INTERNAL_FALLBACK"
                        }
                        # Prepend and deduplicate by title, limit to 15
                        updated_cache = [fixture_entry] + [a for a in current_cache if a.get("headline") != title]
                        await performance_cache.set("recent_news_cache", updated_cache[:15], ttl=300)
                    else:
                        # Standard DB-driven refresh
                        from sqlalchemy import case
                        stmt = (
                            select(News, Sentiment.score, Sentiment.label, Asset.ticker)
                            .join(Sentiment, News.id == Sentiment.news_id)
                            .outerjoin(Asset, Sentiment.asset_id == Asset.id)
                            .order_by(
                                case(
                                    (News.provider.like('%BACKUP%'), 1),
                                    (News.provider.like('%INTERNAL%'), 1),
                                    else_=0
                                ),
                                desc(News.published_at),
                                case(
                                    (News.provider.like('%EVENT_REGISTRY%'), 0),
                                    (News.provider.like('%MARKETAUX%'), 1),
                                    (News.provider.like('%ALPACA%'), 2),
                                    else_=3
                                )
                            )
                            .limit(15)
                        )
                        res = await session.execute(stmt)
                        articles = []
                        for row in res.all():
                            n_obj, s_score, s_label, t_ticker = row
                            provider_val = (n_obj.provider or "UNKNOWN").upper()
                            
                            # Classify article provenance from provider identity
                            # and freshness; older real-provider news is delayed.
                            now = datetime.now(timezone.utc)
                            pub_at = n_obj.published_at
                            if pub_at.tzinfo is None:
                                pub_at = pub_at.replace(tzinfo=timezone.utc)
                            
                            freshness = int((now - pub_at).total_seconds())
                            is_internal = any(x in provider_val for x in ["INTERNAL", "BACKUP", "INJECTION", "FIXTURE"])
                            is_unknown = (provider_val == "UNKNOWN")
                            is_live = (not is_internal) and (not is_unknown) and (freshness < 86400)
                            
                            source_type = "BACKUP_NEWS"
                            if is_live:
                                source_type = "LIVE_PROVIDER"
                            elif not is_internal and not is_unknown:
                                source_type = "DELAYED_PROVIDER"
                            elif is_unknown:
                                source_type = "UNKNOWN_SOURCE"
                            else:
                                source_type = "INTERNAL_FALLBACK"

                            articles.append({
                                "id": n_obj.id,
                                "headline": n_obj.headline,
                                "url": n_obj.url,
                                "timestamp": n_obj.published_at.isoformat() if n_obj.published_at else None,
                                "published_at": n_obj.published_at.isoformat() if n_obj.published_at else None,
                                "last_updated": datetime.fromtimestamp(float(n_obj.ingest_ts or 0.0), timezone.utc).isoformat() if n_obj.ingest_ts else None,
                                "received_at": datetime.fromtimestamp(float(n_obj.ingest_ts or 0.0), timezone.utc).isoformat() if n_obj.ingest_ts else None,
                                "ingest_ts": n_obj.ingest_ts,
                                "sentiment": {"score": float(s_score) if s_score is not None else 0.0, "label": s_label},
                                "asset": t_ticker,
                                "provider": provider_val,
                                "source_type": source_type,
                                "is_live_provider": is_live
                            })
                        
                        if articles:
                            # Latest real news first. Backup/internal stays last.
                            def sort_key(a):
                                p = a.get("provider", "UNKNOWN").upper()
                                is_backup = 1 if ("BACKUP" in p or "INTERNAL" in p) else 0
                                ts = a.get("timestamp") or ""
                                try:
                                    ts_rank = -datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                                except Exception:
                                    ts_rank = 0
                                if "EVENT_REGISTRY" in p:
                                    provider_rank = 0
                                elif "MARKETAUX" in p:
                                    provider_rank = 1
                                elif "ALPACA" in p:
                                    provider_rank = 2
                                else:
                                    provider_rank = 3
                                return (is_backup, ts_rank, provider_rank)
                            
                            articles.sort(key=sort_key)
                            await performance_cache.set("recent_news_cache", articles[:15], ttl=300)
                except Exception as ce:
                    logger.error(f"Failed to update news cache: {ce}")
                
                logger.info(f"📰 [NEWS][BG][{provider}] {title[:50]}... | Assets: {len(detected_assets)}")

        except Exception as e:
            logger.error(f"Error in background article processing: {e}")

    async def refresh_live_sources_once(self):
        """
        Opportunistically refresh REST news providers for dashboard force-refresh calls.

        Provider calls are still throttled by the normal polling interval so the
        dashboard can stay fresh without hammering free/limited APIs.
        """
        if getattr(self, "_refresh_live_sources_running", False):
            return

        now = time.time()
        tasks = []
        marketaux_last = float(self.source_status["marketaux"].get("last_success_at") or 0.0)
        event_registry_last = float(self.source_status["event_registry"].get("last_success_at") or 0.0)

        if settings.MARKETAUX_API_KEY and now - marketaux_last >= MARKETAUX_POLL_SECONDS:
            tasks.append(self._fetch_marketaux_once())
        if settings.EVENTREGISTRY_API_KEY and now - event_registry_last >= EVENT_REGISTRY_POLL_SECONDS:
            tasks.append(self._fetch_event_registry_once())
        if not tasks:
            return

        self._refresh_live_sources_running = True
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self._refresh_live_sources_running = False

    async def _fetch_marketaux_once(self):
        token = settings.MARKETAUX_API_KEY
        if not token: 
            logger.info("[NEWS][IDLE] Marketaux Key missing.")
            self.source_status["marketaux"]["status"] = "INVALID_KEY"
            return
        start_time = time.perf_counter()
        try:
            params = {
                "api_token": token, 
                "symbols": "BTC,ETH,AAPL,TSLA,MSFT,NVDA,AMZN,GOOGL,META,SPY,QQQ", 
                "language": "en", 
                "limit": 20,
                "published_after": (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S"),
                "sort": "published_at"
            }
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                # Poll Marketaux directly; rate/plan limits are reflected in
                # source_status instead of hidden behind fallback data.
                r = await client.get("https://api.marketaux.com/v1/news/all", params=params)
                self.source_status["marketaux"]["latency_ms"] = int((time.perf_counter() - start_time) * 1000)
                
                if r.status_code == 200:
                    self.source_status["marketaux"]["status"] = "CONNECTED"
                    self.source_status["marketaux"]["last_success_at"] = time.time()
                    self.source_status["marketaux"]["last_error_code"] = None
                    items = sorted(
                        r.json().get("data", []),
                        key=lambda item: _provider_timestamp(item.get("published_at")),
                        reverse=True,
                    )
                    for item in items:
                        pub_at = item.get("published_at")
                        pub_ts = datetime.fromisoformat(pub_at.replace("Z", "+00:00")).timestamp() if pub_at else time.time()
                        await self.process_article({
                            "provider": "MARKETAUX", 
                            "title": item.get("title"), 
                            "summary": item.get("description"),
                            "url": item.get("url"), 
                            "source_ts": pub_ts, 
                            "raw": item
                        })
                else:
                    self.source_status["marketaux"]["last_error_code"] = r.status_code
                    # Store only a short sanitized provider error summary.
                    try:
                        err_body = r.json()
                        self.source_status["marketaux"]["last_error_message_sanitized"] = json.dumps(err_body)[:200]
                    except:
                        self.source_status["marketaux"]["last_error_message_sanitized"] = r.text[:200]
                        
                    if r.status_code == 401: self.source_status["marketaux"]["status"] = "AUTH_FAILED"
                    elif r.status_code == 402: self.source_status["marketaux"]["status"] = "USAGE_LIMIT_REACHED"
                    elif r.status_code == 403: self.source_status["marketaux"]["status"] = "PLAN_RESTRICTED"
                    elif r.status_code == 429: self.source_status["marketaux"]["status"] = "RATE_LIMITED"
                    elif r.status_code >= 500: self.source_status["marketaux"]["status"] = "PROVIDER_ERROR"
                    else: self.source_status["marketaux"]["status"] = "DISCONNECTED"
        except Exception as e:
            self.source_status["marketaux"]["status"] = "NETWORK_RESTRICTED"
            self.source_status["marketaux"]["last_error_message_sanitized"] = str(e)[:100]
            logger.warning(f"[MARKETAUX] Polling Error: {e}")

    async def _poll_marketaux(self):
        if not settings.MARKETAUX_API_KEY:
            logger.info("[NEWS][IDLE] Marketaux Key missing.")
            self.source_status["marketaux"]["status"] = "INVALID_KEY"
            return
        while self.is_running:
            await self._fetch_marketaux_once()
            await asyncio.sleep(MARKETAUX_POLL_SECONDS) # Frequent enough for defense demos; still provider-throttled.

    async def _fetch_event_registry_once(self):
        token = settings.EVENTREGISTRY_API_KEY
        if not token: 
            logger.info("[NEWS][IDLE] Event Registry Key missing.")
            self.source_status["event_registry"]["status"] = "INVALID_KEY"
            return
        start_time = time.perf_counter()
        try:
            # Use Event Registry / NewsAPI.ai article search for broad
            # financial coverage when credentials and plan limits allow it.
            payload = {
                "apiKey": token,
                "action": "getArticles",
                "keyword": ["crypto", "finance", "stock market", "bitcoin", "ethereum", "NASDAQ", "Wall Street"],
                "keywordOper": "or",
                "lang": "eng",
                "sourceGroupUri": "business/top100",
                "articlesPage": 1,
                "articlesCount": 25,
                "articlesSortBy": "date",
                "articlesSortByAsc": False,
                "resultType": "articles",
                "dataType": ["news", "pr"],
                "forceMaxDataTimeWindow": 7
            }
            async with httpx.AsyncClient(timeout=15, verify=False) as client:
                # Provider response status drives health labels for the admin API.
                r = await client.post("https://eventregistry.org/api/v1/article/getArticles", json=payload)
                self.source_status["event_registry"]["latency_ms"] = int((time.perf_counter() - start_time) * 1000)
                
                if r.status_code == 200:
                    self.source_status["event_registry"]["status"] = "CONNECTED"
                    self.source_status["event_registry"]["last_success_at"] = time.time()
                    self.source_status["event_registry"]["last_error_code"] = None
                    data = r.json()
                    articles = sorted(
                        data.get("articles", {}).get("results", []),
                        key=lambda item: _provider_timestamp(item.get("dateTimePub")),
                        reverse=True,
                    )
                    for item in articles:
                        pub_at = item.get("dateTimePub")
                        pub_ts = datetime.fromisoformat(pub_at.replace("Z", "+00:00")).timestamp() if pub_at else time.time()
                        await self.process_article({
                            "provider": "EVENT_REGISTRY", 
                            "title": item.get("title"), 
                            "summary": item.get("body")[:500] if item.get("body") else "",
                            "url": item.get("url"), 
                            "source_ts": pub_ts, 
                            "raw": item
                        })
                else:
                    self.source_status["event_registry"]["last_error_code"] = r.status_code
                    # Store only a short sanitized provider error summary.
                    try:
                        err_body = r.json()
                        self.source_status["event_registry"]["last_error_message_sanitized"] = json.dumps(err_body)[:200]
                    except:
                        self.source_status["event_registry"]["last_error_message_sanitized"] = r.text[:200]

                    if r.status_code == 401: self.source_status["event_registry"]["status"] = "AUTH_FAILED"
                    elif r.status_code == 403: self.source_status["event_registry"]["status"] = "PLAN_RESTRICTED"
                    elif r.status_code == 429: self.source_status["event_registry"]["status"] = "RATE_LIMITED"
                    elif r.status_code >= 500: self.source_status["event_registry"]["status"] = "PROVIDER_ERROR"
                    else: self.source_status["event_registry"]["status"] = "DISCONNECTED"
        except Exception as e:
            self.source_status["event_registry"]["status"] = "NETWORK_RESTRICTED"
            self.source_status["event_registry"]["last_error_message_sanitized"] = str(e)[:100]
            logger.warning(f"[EVENT_REGISTRY] Polling Error: {e}")

    async def _poll_event_registry(self):
        if not settings.EVENTREGISTRY_API_KEY:
            logger.info("[NEWS][IDLE] Event Registry Key missing.")
            self.source_status["event_registry"]["status"] = "INVALID_KEY"
            return
        while self.is_running:
            await self._fetch_event_registry_once()
            await asyncio.sleep(EVENT_REGISTRY_POLL_SECONDS) # Frequent enough for defense demos; still provider-throttled.

    async def _poll_backup_news_generator(self):
        events = [
            {"title": "Federal Reserve signals potential rate pivot in Q3", "provider": "BACKUP_MACRO_FEED", "tickers": []},
            {"title": "AAPL: Tech giants report surge in AI infrastructure demand", "provider": "BACKUP_EQUITY_FEED", "tickers": ["AAPL"]},
            {"title": "Oil prices stabilize amid global supply chain shifts", "provider": "BACKUP_ENERGY_FEED", "tickers": []},
            {"title": "BTCUSDT accumulation trend reaches multi-year high", "provider": "BACKUP_CRYPTO_FEED", "tickers": ["BTCUSDT"]},
            {"title": "Gold (XAUUSD) hits new resistance level as dollar fluctuates", "provider": "BACKUP_METALS_FEED", "tickers": ["XAUUSD"]},
            {"title": "EURUSD parity in sight after latest ECB commentary", "provider": "BACKUP_FOREX_FEED", "tickers": ["EURUSD"]},
            {"title": "ETHUSDT network upgrade fuels bullish sentiment among validators", "provider": "BACKUP_CRYPTO_FEED", "tickers": ["ETHUSDT"]}
        ]
        import random
        while self.is_running:
            selected = random.choice(events)
            title = f"[BACKUP NEWS] {selected['title']} [{time.time()}]"
            if random.random() > 0.8:
                title = f"BREAKING: {title}"
            
            await self.process_article({
                "provider": selected["provider"], 
                "title": title,
                "summary": "Financial analysis for system verification.",
                "source_ts": time.time() - 30,
                "raw": {"system": True}
            })
            self.source_status["backup_news"]["last_success_at"] = time.time()
            await asyncio.sleep(15) # Fast enough for demos; still labeled fallback.

    async def run(self):
        logger.info(f"News Ingest Engine Online (Mode: {'LIVE_VERIFY' if settings.LIVE_VERIFY_MODE else 'NORMAL'}).")
        await redis_bus.connect()
        await self.load_assets()
        
        tasks = []
        if settings.LIVE_VERIFY_MODE or settings.ENABLE_LIVE_NEWS:
            tasks.append(self._poll_marketaux())
            tasks.append(self._poll_event_registry())
            # Alpaca Real-Time News Stream
            alpaca_news = AlpacaNewsProvider(self.process_article, self.update_provider_status)
            tasks.append(alpaca_news.start())
            
        if settings.ENABLE_NEWS_BACKUP_MODE and not settings.LIVE_VERIFY_MODE:
            tasks.append(self._poll_backup_news_generator())
            
        tasks.append(self._periodic_health_check())
             
        await asyncio.gather(*tasks, return_exceptions=True)

    async def start_polling(self):
        """Alias for run() to match API control naming."""
        await self.run()

    def stop(self):
        """Graceful shutdown flag."""
        self.is_running = False
        logger.info("News Ingest Engine shutdown requested.")

    async def _infer_source_health_from_database(self):
        """
        Infer news provider health from recently persisted live news so API
        workers still show the active providers after process restarts.
        """
        now = time.time()

        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(News.provider, News.published_at, News.ingest_ts)
                    .order_by(desc(News.published_at))
                    .limit(50)
                )
                rows = (await session.execute(stmt)).all()
        except Exception:
            return

        for provider, published_at, ingest_ts in rows:
            provider_name = str(provider or "").upper()
            if "BACKUP" in provider_name or "INTERNAL" in provider_name:
                continue

            if "ALPACA" in provider_name:
                provider_key = "alpaca_news"
            elif "MARKETAUX" in provider_name:
                provider_key = "marketaux"
            elif "EVENT" in provider_name:
                provider_key = "event_registry"
            else:
                continue

            if provider_key not in self.source_status:
                continue

            ts = float(ingest_ts or 0.0)
            if ts <= 0 and published_at:
                ts = published_at.timestamp()

            if ts <= 0 or now - ts > 3600:
                continue

            current_last = float(self.source_status[provider_key].get("last_success_at") or 0.0)
            if ts >= current_last:
                self.source_status[provider_key]["status"] = "CONNECTED"
                self.source_status[provider_key]["last_success_at"] = ts
                self.source_status[provider_key]["last_ingest_ts"] = ts
                self.source_status[provider_key]["last_error_code"] = None
                self.source_status[provider_key]["last_error_message_sanitized"] = None

    async def get_source_health(self):
        """
        Return standardized news provider health for API/admin endpoints.

        Live providers, delayed providers, rate/plan limits, stale state, and
        internal fallback are reported separately so dashboard provenance is honest.
        """
        await self._infer_source_health_from_database()
        now = time.time()
        health = {}
        for src, status in self.source_status.items():
            try:
                last_ts = float(status.get("last_success_at") or 0.0)
            except (ValueError, TypeError):
                last_ts = 0.0
            
            # Determine last_ingest_ts for legacy compatibility
            try:
                last_ingest_ts = float(status.get("last_ingest_ts") or 0.0)
            except (ValueError, TypeError):
                last_ingest_ts = 0.0
            if last_ingest_ts == 0.0 and last_ts > 0.0:
                last_ingest_ts = last_ts

            # News is allowed a longer freshness window than market ticks.
            is_stale = not (last_ts > 0 and (now - last_ts) < 1800)
            st = status.get("status", "DISCONNECTED")
            
            # If explicit error status, keep it
            if status.get("last_error_code") in [401, 403]:
                st = "AUTH_FAILED"
            elif status.get("last_error_code") == 429:
                st = "RATE_LIMITED"

            # Only external providers with recent success count as connected.
            external_live_statuses = ["CONNECTED", "LIVE_PROVIDER", "DELAYED_PROVIDER"]
            connected = (st in external_live_statuses) and (not is_stale)
            
            # Internal fallback is available continuity content, not a live provider.
            if st == "INTERNAL_FALLBACK" or src == "backup_news":
                st = "INTERNAL_FALLBACK"
                connected = False
                is_stale = False # Fallback availability is not a provider outage.

            # Reliability summarizes source quality for the admin heartbeat table.
            if st in ["AUTH_FAILED", "RATE_LIMITED", "NETWORK_RESTRICTED", "ERROR"]:
                reliability = "ERROR"
            elif is_stale:
                reliability = "STALE"
            elif st == "INTERNAL_FALLBACK":
                reliability = "FALLBACK"
            else:
                reliability = "HEALTHY"

            health[src] = {
                "provider": status.get("provider", src.upper()),
                "category": status.get("category", "NEWS"),
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
        """Pushes local news provider health to Redis for cross-worker visibility."""
        try:
            health = await self.get_source_health()
            if health:
                await redis_bus.set("news:source_health", json.dumps(health), ex=300)
        except Exception as e:
            logger.error(f"Failed to sync news health to Redis: {e}")

    async def _periodic_health_check(self):
        """Ensures news health status is synced even between provider polls."""
        while self.is_running:
            await self._sync_health_to_redis()
            await asyncio.sleep(10)

news_ingester = NewsIngester()
