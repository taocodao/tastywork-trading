"""
Contract Ranker
===============
ML-powered ranking of liquidity-filtered TQQQ option strike/expiry
candidates. After hard rule filters in SpreadBuilder, this model
scores each candidate by its expected risk-adjusted P&L.

Input : list of candidate contracts (dicts) + current market context
Output: ranked list with scores, best candidate at index 0
"""

import logging
import os
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    xgb = None
    XGB_AVAILABLE = False

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    joblib = None
    JOBLIB_AVAILABLE = False

MODEL_PATH = "src/tqqq/ml/models/contract_ranker.ubj"


@dataclass
class RankedContract:
    contract: Dict[str, Any]
    score: float          # higher is better
    rank: int


class ContextualBanditContractSelector:
    """
    Ranks liquidity-filtered TQQQ contracts by expected risk-adjusted P&L
    using a Contextual Bandit (Thompson Sampling via Ridge Regression).
    Balances exploration of new strike combinations with exploitation of known winners.
    """

    DTE_BUCKETS = [(21, 28), (29, 35), (36, 45)]

    def __init__(self):
        self.n_observations = 0
        # Thompson Sampling parameters (Bayesian Linear Regression)
        # B = inverse covariance matrix, f = B * mu
        self.n_features = 17 
        self.B = np.eye(self.n_features)
        self.f = np.zeros(self.n_features)
        self.sigma = 1.0  # exploration parameter
        
        self.fallback_model = None
        self._try_load()

    # ─────────────────────── Public API ──────────────────────────────────

    def rank(
        self,
        candidates: List[Dict[str, Any]],
        market_context: Dict[str, Any],
    ) -> List[RankedContract]:
        """
        Rank a list of spread candidates using Thompson Sampling.
        """
        if not candidates:
            return []

        # Convert state to features
        feature_dicts = [self._build_features(c, market_context) for c in candidates]
        X = np.array([list(f.values()) for f in feature_dicts])

        # If we have very little data, fallback to raw heuristic score
        if self.n_observations < 20:
            scores = [f["reward_to_risk"] * f["liquidity_score"] for f in feature_dicts]
        else:
            # Thompson Sampling: sample weights from posterior
            B_inv = np.linalg.inv(self.B)
            mu = B_inv @ self.f
            # Sample weights theta from N(mu, sigma^2 * B_inv)
            try:
                theta = np.random.multivariate_normal(mu, self.sigma**2 * B_inv)
            except ValueError:
                theta = mu # Fallback if matrix goes non-PD
            
            # Score arms
            scores = X @ theta

        # Zip and sort by score descending
        ranked = sorted(zip(candidates, scores), key=lambda t: t[1], reverse=True)
        
        return [
            RankedContract(contract=c, score=round(s, 4), rank=i + 1)
            for i, (c, s) in enumerate(ranked)
        ]

    def update(self, context_features: Dict[str, float], reward: float) -> None:
        """
        Update the bandit posterior after a target trade is closed and P/L is known.
        """
        x = np.array(list(context_features.values()))
        # Update inverse covariance and target vector
        self.B += np.outer(x, x)
        self.f += x * reward
        self.n_observations += 1
        self._try_save()

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Batch train the bandit on historical data."""
        for i in range(len(X)):
            self.B += np.outer(X[i], X[i])
            self.f += X[i] * y[i]
            self.n_observations += 1
        self._try_save()
        logger.info(f"Bandit batch trained on {len(X)} historical samples.")

    # ─────────────────────── Feature Engineering ─────────────────────────

    def _build_features(
        self,
        contract: Dict[str, Any],
        ctx: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        Returns a robust dictionary of features (17 features) for one contract context.
        """
        underlying = float(ctx.get("tqqq_price", 50.0))
        strike     = float(contract.get("strike", underlying))
        
        bid   = float(contract.get("bid", 0.5))
        ask   = float(contract.get("ask", 0.6))
        
        credit      = float(contract.get("credit", 0.50))
        max_loss    = float(contract.get("max_loss", 4.50))
        
        regime_map  = {"LOW_VOL": 0, "NORMAL": 1, "HIGH_VOL": 2, "CRISIS": 3}
        dir_map     = {"VIX_FALLING": -1, "NEUTRAL": 0, "VIX_RISING": 1}

        return {
            "delta": abs(float(contract.get("delta", 0.25))),
            "gamma": abs(float(contract.get("gamma", 0.01))),
            "theta": abs(float(contract.get("theta", 0.05))),
            "vega": abs(float(contract.get("vega", 0.10))),
            "iv": float(contract.get("iv", 0.60)),
            "moneyness": strike / underlying if underlying > 0 else 1.0,
            "dte_bucket": float(self._dte_bucket(int(contract.get("dte", 30)))),
            "bid_ask_spread_norm": (ask - bid) / max(bid, 0.01),
            "volume_norm": float(contract.get("volume", 1000)) / 5000.0,
            "oi_norm": float(contract.get("open_interest", 2000)) / 10000.0,
            "bid_size_norm": float(contract.get("bid_size", 50)) / 100.0,
            "iv_minus_hv": float(contract.get("iv", 0.60)) - float(ctx.get("tqqq_hv20", 0.80)),
            "vix_regime_int": float(regime_map.get(ctx.get("regime", "NORMAL"), 1)),
            "vix_direction_int": float(dir_map.get(ctx.get("vix_direction", "NEUTRAL"), 0)),
            "reward_to_risk": credit / max(max_loss, 0.01),
            "credit_norm": credit / 2.0,
            "liquidity_score": float(contract.get("liquidity_score", 0.5))
        }

    @staticmethod
    def _dte_bucket(dte: int) -> int:
        if dte <= 28:
            return 0
        elif dte <= 35:
            return 1
        return 2

    # ─────────────────────── Persistence ─────────────────────────────────

    def _try_load(self) -> None:
        if JOBLIB_AVAILABLE and os.path.exists(MODEL_PATH):
            try:
                state = joblib.load(MODEL_PATH)
                self.B = state['B']
                self.f = state['f']
                self.n_observations = state['n_observations']
                logger.info(f"Bandit state loaded ← {MODEL_PATH}")
            except Exception as exc:
                logger.warning(f"Could not load bandit state: {exc}")

    def _try_save(self) -> None:
        if JOBLIB_AVAILABLE:
            try:
                os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
                joblib.dump({
                    'B': self.B, 
                    'f': self.f, 
                    'n_observations': self.n_observations
                }, MODEL_PATH)
            except Exception as exc:
                logger.warning(f"Could not save bandit state: {exc}")

