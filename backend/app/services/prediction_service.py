"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Provides prediction service helpers that connect market history to model output.
"""
import logging
import os
from typing import Optional, List, Any

logger = logging.getLogger("PredictionService")

class PredictionService:
    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        self.model_path = model_path
        self._is_ready = False

    def _ensure_model(self):
        if self._is_ready:
            return
        import xgboost as xgb
        if self.model_path and os.path.exists(self.model_path):
            try:
                self.model = xgb.Booster()
                self.model.load_model(self.model_path)
                logger.info(f"Loaded pre-trained model from {self.model_path}")
                self._is_ready = True
            except Exception as e:
                logger.error(f"Failed to load model {self.model_path}: {e}")
                self.model = None
                self._is_ready = False
        else:
            logger.warning(f"Model path missing or invalid: {self.model_path}. ML signal unavailable.")
            self.model = None
            self._is_ready = False

    def _train_real_model(self):
        """DEPRECATED: Runtime training is disabled for production hardening."""
        logger.warning("Attempted to call deprecated _train_real_model(). Ignoring.")
        pass

    def predict_direction(self, features: List[Any]):
        """
        Predicts price direction (1: UP, 0: DOWN)
        Expected Features: [sentiment, volatility, volume_delta]
        """
        self._ensure_model()
        import xgboost as xgb
        import numpy as np
        if not self.model:
            return None, None
            
        dmatrix = xgb.DMatrix(np.array([features]))
        prob = self.model.predict(dmatrix)[0]
        
        prediction = 1 if prob > 0.5 else 0
        return prediction, float(prob)
