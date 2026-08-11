"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Detects market events from news and sentiment to support recommendation reasoning.
"""
import re
from typing import Tuple, List
from loguru import logger
from app.models.all_models import Event

class EventDetector:
    def __init__(self):
        # Deterministic keyword mappings for event classification
        self.categories = {
            "Merger/Acquisition": ["acquire", "acquired", "acquisition", "merger", "buyout", "takeover"],
            "Earnings": ["earnings", "revenue", "guidance", "quarterly results", "profit", "net income", "fiscal"],
            "Regulatory": ["regulation", "regulator", "regulatory", "lawsuit", "sec", "ban", "approval", "compliance", "fine", "scrutiny"],
            "Macro": ["fed", "central bank", "rates", "interest rates", "inflation", "cpi", "ecb", "monetary"],
            "Supply Chain": ["oil", "supply chain", "production cut", "opec", "energy", "shortage", "logistics"],
            "Crypto/Network": ["upgrade", "fork", "validators", "staking", "on-chain", "halving", "mainnet"]
        }

    def detect_event(self, text: str) -> Tuple[str, List[str]]:
        """
        Scans text for keywords and returns the highest-priority category and matched keywords.
        Returns ("Market", []) if no specific category matches.
        """
        matches = {}
        for category, keywords in self.categories.items():
            found = []
            for kw in keywords:
                # Use word boundaries for exact matching
                pattern = rf"\b{re.escape(kw)}\b"
                if re.search(pattern, text, re.IGNORECASE):
                    found.append(kw)
            if found:
                matches[category] = found

        if not matches:
            return "Market", []

        # Priority: Pick the category with the most keyword matches
        # If tied, the order in self.categories defines priority
        best_cat = max(matches, key=lambda k: len(matches[k]))
        return best_cat, matches[best_cat]

    def create_event_model(self, news_id: int, asset_id: int, headline: str) -> Event:
        """Helper to create the SQLAlchemy model instance."""
        event_type, keywords = self.detect_event(headline)
        
        # Calculate magnitude (internal for now, could be based on sentiment or keyword intensity)
        # For this step, we keep it simple as requested.
        magnitude = 0.5 + (0.1 * len(keywords))
        
        logger.info(f"🎯 Event Detected: [{event_type}] | Keywords: {keywords} | Headline: {headline[:50]}...")
        
        return Event(
            news_id=news_id,
            asset_id=asset_id,
            event_type=event_type,
            magnitude=min(magnitude, 1.0)
        )

    async def detect_and_persist(self, news_obj, asset_id: int, session):
        """High-level entry point to detect, create, and add to session."""
        # 🛡️ FIX: Persistence is now permitted even for NULL asset_id (Macro/General News)
        
        event = self.create_event_model(
            news_id=news_obj.id,
            asset_id=asset_id,
            headline=news_obj.headline
        )
        # Only persist if it's not a generic 'Market' event (optional refinement)
        if event.event_type != "Market":
            session.add(event)
            return event
        return None

event_detector = EventDetector()
