"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Implements explainable portfolio rebalancing across low, medium, and high risk profiles.
- Produces BUY/SELL/HOLD suggestions with drift, confidence, and price-source context.
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("RebalanceService")

class RebalanceService:
    """
    Implement deterministic risk-profile allocation and rebalance advice.

    Target class weights are transparent, drift thresholds are adaptive, and
    confidence is adjusted by both allocation drift and market data source quality.
    """
    
    # 12 Supported Assets
    SUPPORTED_TICKERS = [
        "AAPL", "TSLA", "BTC/USD", "ETH/USD", 
        "XAU/USD", "XAG/USD", "EUR/USD", "GBP/USD", 
        "USD/TRY", "USD/JPY", "WTI", "BRENT"
    ]
    
    # Asset Classification
    ASSET_CLASSES = {
        "STOCKS": ["AAPL", "TSLA"],
        "CRYPTO": ["BTC/USD", "ETH/USD"],
        "METALS": ["XAU/USD", "XAG/USD"],
        "FOREX": ["EUR/USD", "GBP/USD", "USD/TRY", "USD/JPY"],
        "ENERGY": ["WTI", "BRENT"]
    }

    def get_target_allocation(self, risk_profile: str) -> Dict[str, float]:
        """
        Return target asset-class weights for LOW, MEDIUM, or HIGH risk profiles.

        The result includes CASH and sums to 1.0 so portfolio value can be
        allocated consistently across all supported asset sleeves.
        """
        risk_profile = risk_profile.upper()
        
        if risk_profile == "LOW":
            return {
                "CASH": 0.30,
                "METALS": 0.20,
                "FOREX": 0.20,
                "STOCKS": 0.20,
                "ENERGY": 0.05,
                "CRYPTO": 0.05
            }
        elif risk_profile == "HIGH":
            return {
                "CASH": 0.05,
                "CRYPTO": 0.40,
                "STOCKS": 0.35,
                "METALS": 0.10,
                "ENERGY": 0.05,
                "FOREX": 0.05
            }
        else: # MEDIUM (Default)
            return {
                "CASH": 0.15,
                "STOCKS": 0.30,
                "CRYPTO": 0.20,
                "METALS": 0.15,
                "FOREX": 0.10,
                "ENERGY": 0.10
            }

    def get_asset_class(self, ticker: str) -> str:
        """
        Return the allocation sleeve for a supported ticker.

        Rebalance logic operates at the asset-class level, so each ticker must
        map to the same class used by target allocation profiles.
        """
        for cls, tickers in self.ASSET_CLASSES.items():
            if ticker.upper() in tickers:
                return cls
        return "OTHER"

    def _rebalance_threshold(self, target_weight: float) -> float:
        """
        Uses a smaller tolerance band for small target allocations so a 1.25%
        target sleeve is still actionable when it is completely missing.
        """
        if target_weight <= 0:
            return 0.005
        return min(0.02, max(0.005, target_weight * 0.25))

    def _action_from_drift(self, drift: float, threshold: float) -> str:
        """
        Convert allocation drift into BUY, SELL, or HOLD.

        Positive drift means the portfolio is under target; negative drift means
        it is over target. The threshold prevents tiny differences from creating
        noisy rebalance suggestions.
        """
        if drift > threshold:
            return "BUY"
        if drift < -threshold:
            return "SELL"
        return "HOLD"

    def _confidence_from_drift(self, drift: float, threshold: float, source_label: str) -> float:
        """
        Confidence reflects how far the portfolio is outside the rebalance band.
        Fallback/missing prices cap confidence because the signal is less tradable.
        """
        scale = min(abs(drift) / max(threshold, 0.0001), 4.0)
        drift_strength = scale / 4.0
        confidence = 0.50 + (drift_strength * 0.22) + (min(abs(drift), 0.20) * 0.40)

        source_upper = str(source_label or "").upper()
        if source_upper == "MISSING":
            confidence = 0.10
        elif source_upper in {"INTERNAL_FALLBACK", "UNKNOWN"}:
            confidence = min(confidence, 0.55)
        elif "HISTORY" in source_upper:
            confidence = min(confidence, 0.68)
        elif "HISTORY" in source_upper or "DELAY" in source_upper:
            confidence = min(confidence, 0.82)
        else:
            confidence = min(confidence, 0.95)

        return round(confidence, 2)

    def _build_reasoning(
        self,
        risk_profile: str,
        asset_class: str,
        action: str,
        drift: float,
        threshold: float,
        price_available: bool,
    ) -> str:
        """
        Build the short dashboard explanation for one rebalance suggestion.

        The explanation connects risk profile, asset class target, allocation
        drift, and price availability so suggestions are transparent to users.
        """
        if not price_available:
            return "Price unavailable; holding until a verified market price is available."

        drift_pp = drift * 100
        threshold_pp = threshold * 100

        if action == "BUY":
            return (
                f"Under target by {drift_pp:.2f} percentage points; buy toward "
                f"{asset_class} allocation for {risk_profile} risk profile."
            )
        if action == "SELL":
            return (
                f"Over target by {abs(drift_pp):.2f} percentage points; sell down toward "
                f"{asset_class} allocation for {risk_profile} risk profile."
            )
        return (
            f"Within the {threshold_pp:.2f} percentage-point rebalance band; hold current "
            f"{asset_class} exposure."
        )

    async def calculate_rebalance(
        self,
        portfolio: Any,
        current_prices: Dict[str, float],
        current_sources: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Calculate BUY/SELL/HOLD suggestions for every supported ticker.

        Inputs are the portfolio, current price map, and source-quality labels.
        Output rows include drift, target/current value, trade size, and reasoning
        for the frontend AI Rebalance Intelligence panel.
        """
        risk_profile = str(portfolio.risk_profile or "MEDIUM").upper()
        target_class_weights = self.get_target_allocation(risk_profile)
        total_value = float(getattr(portfolio, 'dynamic_total_value', portfolio.total_value) or 0.0)
        current_sources = current_sources or {}
        
        suggestions = []
        
        # Calculate current weights
        current_holdings = {
            a.asset.ticker: float(a.quantity or 0.0)
            for a in portfolio.assets
            if getattr(a, "asset", None) is not None
        }
        
        # Distribution of weights within a class (equal weight for simplicity in this version)
        for ticker in self.SUPPORTED_TICKERS:
            asset_class = self.get_asset_class(ticker)
            class_target_weight = target_class_weights.get(asset_class, 0)
            
            # Number of assets in this class
            class_assets_count = len(self.ASSET_CLASSES.get(asset_class, []))
            target_weight = class_target_weight / class_assets_count if class_assets_count > 0 else 0
            
            price = float(current_prices.get(ticker) or 0.0)
            qty = current_holdings.get(ticker, 0.0)
            source_label = current_sources.get(ticker, "UNKNOWN")
            price_available = price > 0
            current_value = qty * price if price_available else 0.0
            current_weight = current_value / total_value if total_value > 0 else 0.0
            target_value = total_value * target_weight if total_value > 0 else 0.0
            drift = target_weight - current_weight
            threshold = self._rebalance_threshold(target_weight)
            action = self._action_from_drift(drift, threshold) if price_available else "HOLD"
            trade_value = target_value - current_value if price_available else 0.0
            trade_quantity = trade_value / price if price_available else 0.0
            confidence = self._confidence_from_drift(drift, threshold, source_label) if price_available else 0.10
            
            # Risk-based reasoning
            risk_reason = self._get_risk_reason(risk_profile, asset_class, action)
            reasoning = self._build_reasoning(
                risk_profile,
                asset_class,
                action,
                drift,
                threshold,
                price_available,
            )
            
            suggestions.append({
                "ticker": ticker,
                "current_weight": round(current_weight, 4),
                "target_weight": round(target_weight, 4),
                "drift": round(drift, 4),
                "threshold": round(threshold, 4),
                "action": action,
                "confidence": confidence,
                "reasoning": reasoning,
                "risk_adjustment_reason": risk_reason,
                "price_used": round(price, 6),
                "price_source": source_label,
                "current_value": round(current_value, 2),
                "target_value": round(target_value, 2),
                "trade_value": round(trade_value, 2),
                "trade_quantity": round(trade_quantity, 6),
                "price_available": price_available
            })
            
        return suggestions

    def _get_risk_reason(self, risk_profile: str, asset_class: str, action: str) -> str:
        """
        Return a risk-profile explanation for the target asset class.

        This is separate from drift reasoning so the dashboard can explain both
        why an asset belongs in the profile and why a BUY/SELL/HOLD was suggested.
        """
        risk_profile = str(risk_profile or "MEDIUM").upper()
        if risk_profile == "LOW":
            if asset_class in ["METALS", "FOREX"]:
                return "Defensive positioning in low-volatility assets."
            if asset_class == "CRYPTO":
                return "Crypto exposure is capped for low-risk defensive allocation."
        if risk_profile == "HIGH":
            if asset_class in ["CRYPTO", "STOCKS"]:
                return "Aggressive allocation for maximum growth potential."
            if asset_class in ["METALS", "FOREX", "ENERGY"]:
                return "Secondary diversification sleeve for high-risk allocation."
        return "Maintaining balanced portfolio allocation."

rebalance_service = RebalanceService()
