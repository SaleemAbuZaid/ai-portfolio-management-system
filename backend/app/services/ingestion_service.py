"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Coordinates ingestion-related service entry points for market and news data.
"""
import feedparser
import httpx
from datetime import datetime
from app.core.config import settings

class IngestionService:
    @staticmethod
    async def fetch_rss_news(rss_url: str):
        """Fetches news from configured RSS feeds and verified news providers"""
        # feedparser is synchronous, but we wrap in a simple way
        feed = feedparser.parse(rss_url)
        return feed.entries

    @staticmethod
    async def fetch_finnhub_news(symbol: str):
        """Fetches high-quality financial news from Finnhub REST API"""
        async with httpx.AsyncClient() as client:
            url = f"https://finnhub.io/api/v1/news?category=general&token={settings.FINNHUB_API_KEY}"
            response = await client.get(url)
            return response.json()
