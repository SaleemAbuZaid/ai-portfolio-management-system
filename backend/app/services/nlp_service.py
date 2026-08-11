"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Scores financial news sentiment and extracts NLP signals for AI recommendations.
"""
from app.core.config import settings
import logging

logger = logging.getLogger("NLPService")

class NLPService:
    """
    Scores financial text sentiment with FinBERT when available and heuristic fallback otherwise.

    This service supplies normalized score/label pairs for news ingestion and AI
    recommendations while keeping fallback behavior explicit in the returned method.
    """
    def __init__(self):
        self.tokenizer = None
        self.model = None
        self.torch = None

    def _load_model(self):
        if self.model is not None:
            return
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            import torch
            logger.info(f"Loading FinBERT model: {settings.FINBERT_MODEL_NAME}")
            # Defense Optimization: Force local files if possible
            self.tokenizer = AutoTokenizer.from_pretrained(settings.FINBERT_MODEL_NAME, local_files_only=True)
            self.model = AutoModelForSequenceClassification.from_pretrained(settings.FINBERT_MODEL_NAME, local_files_only=True)
            self.torch = torch
        except Exception as e:
            logger.warning(f"Failed local NLP load, attempting remote: {e}")
            try:
                from transformers import AutoTokenizer, AutoModelForSequenceClassification
                import torch
                self.tokenizer = AutoTokenizer.from_pretrained(settings.FINBERT_MODEL_NAME)
                self.model = AutoModelForSequenceClassification.from_pretrained(settings.FINBERT_MODEL_NAME)
                self.torch = torch
            except Exception as e2:
                logger.error(f"Total NLP failure: {e2}")

    def _heuristic_sentiment(self, text: str):
        """Simple keyword-based sentiment as a fallback/bypass."""
        text = text.lower()
        pos_words = ["bullish", "buy", "up", "gain", "profit", "positive", "growth", "high", "long"]
        neg_words = ["bearish", "sell", "down", "loss", "crash", "negative", "fall", "low", "short"]
        
        score = 0.0
        for word in pos_words:
            if word in text: score += 0.2
        for word in neg_words:
            if word in text: score -= 0.2
            
        score = max(-1.0, min(1.0, score))
        label = "POSITIVE" if score > 0.1 else "NEGATIVE" if score < -0.1 else "NEUTRAL"
        return {"score": score, "label": label, "method": "heuristic"}

    def analyze_sentiment(self, text: str):
        """
        Infers sentiment using FinBERT or Heuristic fallback.
        Returns: {score: float (-1 to 1), label: string}
        """
        # Graduation Defense Optimization: Bypass heavy NLP if configured
        if getattr(settings, "BYPASS_NLP", True):
            return self._heuristic_sentiment(text)

        self._load_model()
        if not self.model or not self.tokenizer:
            return self._heuristic_sentiment(text)

        try:
            import torch.nn.functional as F
            inputs = self.tokenizer(text, return_tensors="pt", truncation=True, padding=True)
            with self.torch.no_grad():
                outputs = self.model(**inputs)
                scores = F.softmax(outputs.logits, dim=1)
                
            # FinBERT labels: 0: neutral, 1: positive, 2: negative
            pos = scores[0][1].item()
            neg = scores[0][2].item()
            
            sentiment_score = pos - neg
            label = "POSITIVE" if sentiment_score > 0.2 else "NEGATIVE" if sentiment_score < -0.2 else "NEUTRAL"
            
            return {"score": sentiment_score, "label": label, "method": "finbert"}
        except Exception as e:
            logger.warning(f"NLP Inference failed, using heuristic: {e}")
            return self._heuristic_sentiment(text)
