"""
Stationary Block Bootstrap (SBB) Generator
============================================
Preserves volatility clustering, regime autocorrelation, and joint
price/IV dynamics — the critical failure mode of naive I.I.D. resampling
for short-options strategies.

Based on: Politis & Romano (1994) "The Stationary Bootstrap"
Uses the `arch` library's StationaryBootstrap implementation.

Key Design Decisions:
- State vector: [log_return, hv_20, iv_rank, vix_pct_rank]
  These four features capture all regime-dependent dynamics for a short-put.
- Mean block length: 20 trading days (≈ vol autocorrelation decay horizon).
  Can be tuned via block_length parameter.
- Outputs: List of resampled feature DataFrames, one per bootstrap path.
  Each path has the same length as the original (so backtest PnL is
  directly comparable across paths).
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _stationary_bootstrap_indices(n: int, block_length: int,
                                   rng: np.random.Generator) -> np.ndarray:
    """
    Generate a sequence of indices following the stationary bootstrap scheme.
    Each block has a geometrically distributed length with mean = block_length.
    
    Args:
        n:            Length of original time series
        block_length: Mean block length (autocorrelation decay window)
        rng:          Numpy random generator for reproducibility
    
    Returns:
        np.ndarray of shape (n,) with resampled integer indices
    """
    p = 1.0 / block_length          # Geometric distribution parameter
    indices = np.empty(n, dtype=int)
    i = 0
    while i < n:
        start = int(rng.integers(0, n))          # Random starting position
        # Geometrically distributed block length
        block_len = int(np.ceil(rng.geometric(p)))
        block_len = min(block_len, n - i)        # Don't overshoot target
        for j in range(block_len):
            indices[i] = (start + j) % n         # Wrap around (circular)
            i += 1
            if i >= n:
                break
    return indices


class StationaryBlockBootstrap:
    """
    Generates multiple resampled versions of a historical feature dataset
    while preserving short-term autocorrelation structure.

    Usage:
        sbb = StationaryBlockBootstrap(features_dict, block_length=20, n_paths=1000)
        for path_features in sbb.generate():
            run_backtest(path_features, params)
    """

    def __init__(
        self,
        features_dict: Dict[str, pd.DataFrame],
        block_length: int = 20,
        n_paths: int = 500,
        seed: Optional[int] = 42,
    ):
        """
        Args:
            features_dict: {symbol: feature_df} from build_all_features()
            block_length:  Mean block length for SBB (20 = ~1 month)
            n_paths:       Number of bootstrap paths to generate
            seed:          Random seed for reproducibility
        """
        self.features_dict = features_dict
        self.block_length  = block_length
        self.n_paths       = n_paths
        self.seed          = seed
        self._rng          = np.random.default_rng(seed)

        # Find the common date range across all symbols
        self._build_joint_index()
        logger.info(
            f"SBB initialized: {len(features_dict)} symbols | "
            f"n={len(self.common_index)} days | "
            f"block_len={block_length} | n_paths={n_paths}"
        )

    def _build_joint_index(self):
        """Build a common DatetimeIndex across all feature DataFrames."""
        indices = [df.index for df in self.features_dict.values() if not df.empty]
        if not indices:
            raise ValueError("features_dict is empty — cannot build joint index.")
        # Intersection: only days where ALL symbols have data
        common = indices[0]
        for idx in indices[1:]:
            common = common.intersection(idx)
        self.common_index = common.sort_values()
        self.n_days = len(self.common_index)

    def _resample_single_symbol(
        self, feat_df: pd.DataFrame, indices: np.ndarray
    ) -> pd.DataFrame:
        """
        Apply a pre-generated bootstrap index array to a single symbol's
        feature DataFrame.

        The date index is PRESERVED (so the backtest engine doesn't need to
        know this is resampled data). Only the row values are shuffled.
        """
        aligned = feat_df.reindex(self.common_index).ffill().bfill()
        resampled_values = aligned.values[indices]
        resampled_df = pd.DataFrame(
            resampled_values,
            index=self.common_index,
            columns=aligned.columns,
        )
        return resampled_df

    def generate(self) -> List[Dict[str, pd.DataFrame]]:
        """
        Generate all bootstrap paths.

        Returns:
            List of feature dicts, each structured identically to
            the original features_dict. Length = n_paths.
        """
        paths = []
        for path_i in range(self.n_paths):
            # Use SAME index array for ALL symbols on this path —
            # this preserves cross-sectional correlations between stocks
            # (e.g. AAPL and SPY both drop together in a crash block)
            idx_array = _stationary_bootstrap_indices(
                self.n_days, self.block_length, self._rng
            )
            path_features = {}
            for symbol, feat_df in self.features_dict.items():
                try:
                    path_features[symbol] = self._resample_single_symbol(
                        feat_df, idx_array
                    )
                except Exception as e:
                    logger.warning(f"SBB [{symbol}] path {path_i}: {e}")
            paths.append(path_features)

            if (path_i + 1) % 100 == 0:
                logger.info(f"  Generated {path_i + 1}/{self.n_paths} SBB paths")

        logger.info(f"SBB complete: {len(paths)} paths ready.")
        return paths

    def generate_single(self) -> Dict[str, pd.DataFrame]:
        """Generate exactly one bootstrap path (useful for testing)."""
        idx_array = _stationary_bootstrap_indices(
            self.n_days, self.block_length, self._rng
        )
        path_features = {}
        for symbol, feat_df in self.features_dict.items():
            try:
                path_features[symbol] = self._resample_single_symbol(
                    feat_df, idx_array
                )
            except Exception as e:
                logger.warning(f"SBB [{symbol}] single path: {e}")
        return path_features

    def validate_autocorrelation(
        self, symbol: str, feature: str = "iv_rank", lags: int = 20
    ) -> Dict[str, float]:
        """
        Diagnostic: compare autocorrelation of original vs one bootstrap path.
        A good SBB preserves autocorrelation at short lags.

        Returns:
            {'original_acf_lag1': float, 'bootstrap_acf_lag1': float}
        """
        if symbol not in self.features_dict:
            return {}
        original = (
            self.features_dict[symbol]
            .reindex(self.common_index)[feature]
            .dropna()
        )
        boot_path = self.generate_single()[symbol][feature].dropna()

        def acf(s, lag):
            return float(s.autocorr(lag=lag)) if len(s) > lag else 0.0

        result = {
            "original_acf_lag1": acf(original, 1),
            "original_acf_lag5": acf(original, 5),
            "bootstrap_acf_lag1": acf(boot_path, 1),
            "bootstrap_acf_lag5": acf(boot_path, 5),
        }
        logger.info(f"SBB ACF validation [{symbol}/{feature}]: {result}")
        return result
