"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Serves latest financial news, sentiment metadata, and truth-audit provenance counts.
- Labels articles as LIVE_PROVIDER, DELAYED_PROVIDER, INTERNAL_FALLBACK, or UNKNOWN_SOURCE.
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.core.redis_client import redis_bus
from datetime import datetime, timezone
import json
import html
import logging
import time
from pydantic import BaseModel
from app.services.ingestion.news_ingester import news_ingester
from app.services.cache_service import performance_cache
from app.services.performance_monitor import record_metric
from app.core.db import AsyncSessionLocal
from app.models.all_models import News, Sentiment, Asset
from sqlalchemy import select, desc

logger = logging.getLogger(__name__)
router = APIRouter()

# Internal fallback content is only used when live/delayed provider data and
# persisted DB history cannot supply any rows. It is always labeled as fallback.
INTERNAL_FALLBACK_NEWS = [
    {
        "id": "internal-1",
        "headline": "Global Market Liquidity Metrics Showing Robust Stability Patterns",
        "url": "https://apex.ai/intelligence/market-liquidity",
        "timestamp": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "provider": "INTERNAL_FALLBACK",
        "source_type": "BACKUP_NEWS",
        "sentiment": {"score": 0.68, "label": "POSITIVE"},
        "asset": "GENERAL"
    },
    {
        "id": "internal-2",
        "headline": "Cross-Asset Correlation Analysis Indicates Strategic Rebalancing Opportunity",
        "url": "https://apex.ai/intelligence/correlation-report",
        "timestamp": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "provider": "INTERNAL_FALLBACK",
        "source_type": "BACKUP_NEWS",
        "sentiment": {"score": 0.55, "label": "NEUTRAL"},
        "asset": "GENERAL"
    },
    {
        "id": "internal-3",
        "headline": "Apex System Audit Verification: News Feed Integrity Confirmed",
        "url": "https://apex.ai/intelligence/audit-integrity",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "provider": "INTERNAL_FALLBACK",
        "source_type": "BACKUP_NEWS",
        "sentiment": {"score": 0.90, "label": "POSITIVE"},
        "asset": "GENERAL"
    }
]

@router.get("/latest")
async def get_latest_news(limit: int = 15, force_refresh: bool = False):
    """
    Return the latest scored headlines for the dashboard news stream.

    The endpoint reads the hot cache first, falls back to persisted DB news, and
    only uses internal continuity rows when no provider-backed news is available.
    Every article carries a provenance label for live, delayed, fallback, or
    unknown source handling.
    """
    articles = []
    source = "unknown"
    
    try:
        # Cache hits are normalized again because older workers may have written
        # partial article shapes before the current dashboard schema existed.
        if not force_refresh:
            cached_news = await performance_cache.get("recent_news_cache")
            if cached_news:
                normalized_cache = prepare_article_list(
                    [normalize_article(a) for a in cached_news],
                    limit,
                )
                
                # Cache responses still include provenance counts for the
                # dashboard footer and Step 7 audit status.
                meta = calculate_audit_metadata(normalized_cache)
                
                return {
                    "status": "success",
                    "articles": normalized_cache,
                    "source": "cache",
                    "count": len(normalized_cache),
                    "metadata": meta
                }
            
        # force_refresh bypasses cache but still returns DB-backed rows because
        # provider polling runs asynchronously in the ingestion worker.
        if force_refresh:
            logger.info("Force refresh requested for news. Bypassing cache.")
            # Pull live REST providers when their throttle window is due, then
            # read the DB-backed truth/audit feed. This keeps the dashboard as
            # fresh as the provider limits allow without fabricating rotation.
            await news_ingester.refresh_live_sources_once()
            source = "force_refresh_db"
        else:
            source = "db"

        # Database rows preserve their original provider names so the API can
        # classify LIVE_PROVIDER, DELAYED_PROVIDER, or INTERNAL_FALLBACK later.
        from sqlalchemy import case
        async with AsyncSessionLocal() as session:
            # Live/delayed providers are sorted ahead of backup/internal rows
            # before the final normalization and deduplication pass.
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
                .limit(limit)
            )
            res = await session.execute(stmt)
            for row in res.all():
                news_obj, score, label, ticker = row
                articles.append(normalize_article({
                    "id": news_obj.id,
                    "headline": news_obj.headline,
                    "url": news_obj.url,
                    "published_at": news_obj.published_at,
                    "ingest_ts": news_obj.ingest_ts,
                    "score": score,
                    "label": label,
                    "ticker": ticker,
                    "provider": news_obj.provider  # Preserve actual DB provider for provenance.
                }))
    except Exception as e:
        logger.error(f"Error in get_latest_news: {e}")
        source = "error_fallback"

    # Do not pad live results with fallback stories. Fallback content appears
    # only when no provider or persisted article survived normalization.
    if len(articles) == 0:
        needed = 10
        for i in range(needed):
            fallback_item = normalize_article(INTERNAL_FALLBACK_NEWS[i % len(INTERNAL_FALLBACK_NEWS)].copy())
            # Ensure timestamp is fresh for UI sorting
            fallback_item["timestamp"] = datetime.now(timezone.utc).isoformat()
            fallback_item["last_updated"] = datetime.now(timezone.utc).isoformat()
            articles.append(fallback_item)
        if source in ["unknown", "db"]:
            source = "internal_fallback"
        elif source == "force_refresh_db":
            source = "force_refresh_failed"

    final_articles = prepare_article_list(articles, limit)

    # Warm the normalized response so the dashboard can refresh frequently
    # without repeating the DB join on every poll.
    try:
        await performance_cache.set("recent_news_cache", final_articles, ttl=15)
    except Exception as ce:
        logger.warning(f"Failed to warm news cache: {ce}")
        
    # Provenance distribution backs the NewsFeed footer and Admin provenance mix.
    meta = calculate_audit_metadata(final_articles)

    return {
        "status": "success", 
        "articles": final_articles, 
        "source": source,
        "count": len(final_articles),
        "metadata": meta
    }

def prepare_article_list(articles: list, limit: int = 15) -> list:
    """
    Deduplicate, filter, and sort normalized articles for display.

    Live and delayed provider articles are preferred; internal fallback rows are
    retained only when needed so the UI does not overstate news provenance.
    """
    deduped = []
    seen = set()
    for article in articles:
        key = (
            str(article.get("url") or "").strip().lower()
            or str(article.get("headline") or "").strip().lower()
        )
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(article)

    display_articles = [
        a for a in deduped
        if (
            a.get("source_type") in ["LIVE_PROVIDER", "DELAYED_PROVIDER"]
            or "VERIFICATION_FIXTURE" in str(a.get("provider", "")).upper()
        )
    ]
    if len(display_articles) >= min(3, limit) or any(
        "VERIFICATION_FIXTURE" in str(a.get("provider", "")).upper() for a in display_articles
    ):
        deduped = display_articles

    # Latest real news appears first; backup/internal rows stay at the end.
    def sort_key(a):
        p = a.get("provider", "UNKNOWN").upper()
        is_backup = 1 if ("BACKUP" in p or "INTERNAL" in p) else 0
        timestamp = a.get("timestamp") or a.get("last_updated") or ""
        try:
            ts_rank = -datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
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
    
    deduped.sort(key=sort_key)
    return deduped[:limit]

def calculate_audit_metadata(articles: list) -> dict:
    """
    Calculate provenance metadata for a list of normalized articles.

    The counts back the Global Intelligence Stream footer and Step 7 checks by
    distinguishing live providers from delayed, fallback, and unknown news.
    """
    live_count = sum(1 for a in articles if a.get("source_type") == "LIVE_PROVIDER")
    delayed_count = sum(1 for a in articles if a.get("source_type") == "DELAYED_PROVIDER")
    backup_count = sum(1 for a in articles if a.get("source_type") == "INTERNAL_FALLBACK")
    unknown_count = sum(1 for a in articles if a.get("source_type") == "UNKNOWN_SOURCE")
    
    provider_distribution = {}
    for a in articles:
        p = a.get("provider", "UNKNOWN")
        provider_distribution[p] = provider_distribution.get(p, 0) + 1

    return {
        "live_count": live_count,
        "delayed_count": delayed_count,
        "fallback_count": backup_count,
        "unknown_count": unknown_count,
        "provider_distribution": provider_distribution,
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "audit_status": "PASS" if live_count > 0 else "FAIL"
    }

def normalize_article(raw_article: dict) -> dict:
    """
    Normalize a raw/cache/DB article into the dashboard news schema.

    The provenance logic is intentionally conservative: internal backup content
    remains INTERNAL_FALLBACK, while real provider news can be LIVE_PROVIDER or
    DELAYED_PROVIDER depending on article freshness.
    """
    now = datetime.now(timezone.utc)
    
    # Handle both object-style DB conversions and dict-style cache/internal rows.
    headline = raw_article.get("headline") or raw_article.get("title") or ""
    url = raw_article.get("url") or ""
    provider = str(raw_article.get("provider") or "UNKNOWN").upper()
    
    # Some legacy cache rows encoded fallback status in the headline. Treat
    # those as INTERNAL_FALLBACK even if the provider field is incomplete.
    headline_lower = headline.lower()
    if "internal fallback" in headline_lower or "backup data" in headline_lower:
        provider = "INTERNAL_FALLBACK"
        is_internal_force = True
    else:
        is_internal_force = False
    
    # Normalize timestamps before freshness-based live/delayed classification.
    pub_at = raw_article.get("published_at") or raw_article.get("timestamp")
    if isinstance(pub_at, str):
        try:
            pub_at = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
        except:
            pub_at = now
    
    if pub_at is None:
        pub_at = now
        
    if pub_at.tzinfo is None:
        pub_at = pub_at.astimezone(timezone.utc)
    else:
        pub_at = pub_at.astimezone(timezone.utc)

    raw_ingest_ts = raw_article.get("ingest_ts")
    try:
        ingest_ts = float(raw_ingest_ts) if raw_ingest_ts is not None else time.time()
    except (TypeError, ValueError):
        ingest_ts = time.time()
    received_at = datetime.fromtimestamp(ingest_ts, timezone.utc)

    article_age = int((now - pub_at).total_seconds())
    ingest_freshness = int((now - received_at).total_seconds())
    
    # Internal/backup feeds are isolated from provider-backed news so free API
    # limits or outages never appear as live external coverage.
    is_internal = is_internal_force or any(x in provider for x in ["INTERNAL", "BACKUP", "INJECTION", "FIXTURE"])
    is_unknown = (provider == "UNKNOWN")
    
    # Truthful live provider status: Must be non-internal, known, and fresh (< 24 hours for news stability)
    is_live = (
        (not is_internal)
        and (not is_unknown)
        and (article_age < 86400 or ingest_freshness < 3600)
    )
    
    source_type = "BACKUP_NEWS"
    if is_live:
        source_type = "LIVE_PROVIDER"
    elif not is_internal and not is_unknown:
        source_type = "DELAYED_PROVIDER"
    elif is_unknown:
        source_type = "UNKNOWN_SOURCE"
    else:
        source_type = "INTERNAL_FALLBACK"
        
    return {
        "id": raw_article.get("id", "unknown"),
        "headline": html.unescape(headline),
        "url": url,
        "timestamp": pub_at.isoformat(),
        "published_at": pub_at.isoformat(),
        "last_updated": received_at.isoformat(),
        "received_at": received_at.isoformat(),
        "ingest_ts": ingest_ts,
        "sentiment": raw_article.get("sentiment") or {
            "score": float(raw_article.get("score", 0.0)),
            "label": raw_article.get("label", "NEUTRAL")
        },
        "asset": raw_article.get("asset") or raw_article.get("ticker") or "GENERAL",
        "provider": provider,
        "source_type": source_type,
        "is_live_provider": is_live,
        "is_backup": is_internal,
        "is_internal_fallback": is_internal or is_unknown,
        "freshness_seconds": max(0, ingest_freshness),
        "article_age_seconds": max(0, article_age),
        "provider_status": "CONNECTED" if is_live else "FALLBACK_MODE"
    }


@router.post("/control/start-polling")
async def start_news_polling(background_tasks: BackgroundTasks):
    """
    Admin endpoint to begin continuous news source polling.
    """
    if news_ingester.is_running:
        return {"status": "Ignored", "detail": "News polling is already running"}
    
    background_tasks.add_task(news_ingester.start_polling)
    return {"status": "Started", "detail": "News polling background task initiated."}

@router.post("/control/stop-polling")
async def stop_news_polling():
    """Request a graceful stop for the continuous news polling loop."""
    news_ingester.stop()
    return {"status": "Stopped", "detail": "News polling gracefully halted."}

class NewsInjection(BaseModel):
    """
    Request schema for manual news injection during validation.

    It supports controlled test headlines without changing live provider
    ingestion behavior or provenance labeling.
    """
    title: str
    provider: str = "injection"
    url: str = "http://verify.apex.ai"
    summary: str = "Internal article for system verification."

@router.post("/inject")
async def inject_news(article: NewsInjection):
    """
    Inject one article into the news pipeline for validation.

    The injected provider name is kept in the payload so downstream provenance
    labeling can mark it honestly rather than treating it as live news.
    """
    await news_ingester.process_article({
        "provider": article.provider,
        "title": article.title,
        "url": article.url,
        "summary": article.summary,
        "source_ts": time.time()
    })
    return {"status": "Injected", "headline": article.title}

