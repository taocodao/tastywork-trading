"""
Combined Signal Generator
=========================

Orchestrator for the two canonical TradeMind strategies:

1. QQQ_LEAPS — Automated QQQ LEAPS + gated PMCC overlay.
   Canonical engine: src/qqq_leaps/canonical/qqq_leaps_enhanced_2y_hourly.py
   (causal regime filtering, walk-forward GBM confidence, NAV-based sizing,
   PMCC gate pmcc_skip_adx_min=16 / VRP 0.9, max 5 contracts per entry).
   Live executor: src/qqq_leaps/canonical/qqq_live_trader.py (hourly, IBKR).

2. TURBOCORE_PRO — ETF-only regime allocator (QQQ/QLD/TQQQ/SGOV), v3.3.
   Canonical engine: src/turbocore_pro/ (two-stage confidence pipeline,
   0.05 hysteresis tier band, skip open/close bars, 15% bull SGOV floor).
   Live executor: src/turbocore_pro/live/paper_trader.py (hourly, IBKR).

All other strategies in this repository (TQQQ, TurboBounce, Zebra, Theta,
Calendar, Diagonal, Vertical, OTM/SNDK, DVO, PMCC standalone, Dual-Core,
EMA-CCI-MACD) are DISABLED as of the canonical-model consolidation.
Their code is kept in-tree for reference but is not scheduled, not
published, and not selectable here.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Canonical strategy lineup — the only strategies this orchestrator will run.
ENABLED_STRATEGIES = ("QQQ_LEAPS", "TURBOCORE_PRO")


@dataclass
class StrategyRecommendation:
    """Recommended strategy with confidence and reasoning."""
    strategy: str  # "QQQ_LEAPS" or "TURBOCORE_PRO"
    confidence: float
    reasoning: str
    signal: Optional[Any] = None  # The actual signal object


class CombinedSignalGenerator:
    """
    Generates signals from the two canonical strategies only.

    - QQQ_LEAPS: options strategy; requires options approval. Produces
      ENTER/EXIT/HOLD signals for deep-ITM long-dated QQQ calls with an
      optional short-call (PMCC) overlay.
    - TURBOCORE_PRO: ETF-only tactical allocator; no options approval
      required. Produces REBALANCE signals with target weights across
      QQQ / QLD / TQQQ / SGOV.

    The two strategies are complementary, not competitive: LEAPS targets
    bullish convexity with options, TurboCore Pro targets drawdown-controlled
    participation with ETFs. Both run hourly during market hours and publish
    independently.
    """

    def __init__(
        self,
        qqq_leaps_enabled: bool = True,
        turbocore_pro_enabled: bool = True,
    ):
        self.qqq_leaps_enabled = qqq_leaps_enabled
        self.turbocore_pro_enabled = turbocore_pro_enabled
        self.generators: Dict[str, Any] = {}

        if qqq_leaps_enabled:
            try:
                from src.qqq_leaps.scanner import QQQLeapsScanner
                self.generators["QQQ_LEAPS"] = QQQLeapsScanner()
                logger.info("QQQ LEAPS scanner initialized")
            except Exception as e:
                logger.warning(f"Could not initialize QQQ LEAPS scanner: {e}")

        if turbocore_pro_enabled:
            try:
                from src.turbocore_pro.base_strategy import TurboCoreProStrategy
                self.generators["TURBOCORE_PRO"] = TurboCoreProStrategy()
                logger.info("TurboCore Pro strategy initialized")
            except Exception as e:
                logger.warning(f"Could not initialize TurboCore Pro strategy: {e}")

    def generate_signal(
        self,
        strategy: str,
        market_data: Dict,
        account_data: Dict,
    ) -> Optional[StrategyRecommendation]:
        """
        Generate a signal from one canonical strategy.

        Args:
            strategy: "QQQ_LEAPS" or "TURBOCORE_PRO"
            market_data: bars/features required by the strategy
            account_data: NAV, risk settings

        Returns:
            StrategyRecommendation or None
        """
        if strategy not in ENABLED_STRATEGIES:
            logger.warning(
                f"Strategy '{strategy}' is not in the canonical lineup "
                f"{ENABLED_STRATEGIES} — request ignored."
            )
            return None

        generator = self.generators.get(strategy)
        if generator is None:
            logger.info(f"{strategy}: generator not available")
            return None

        try:
            if hasattr(generator, "generate_signal"):
                signal = generator.generate_signal(market_data, account_data)
            elif hasattr(generator, "scan"):
                signal = generator.scan(market_data, account_data)
            else:
                logger.error(f"{strategy}: generator has no signal entrypoint")
                return None
        except Exception as e:
            logger.error(f"Error generating {strategy} signal: {e}")
            return None

        if not signal:
            return None

        return StrategyRecommendation(
            strategy=strategy,
            confidence=getattr(signal, "confidence", 0.0),
            reasoning=self._build_reasoning(strategy, signal),
            signal=signal,
        )

    def generate_all_signals(
        self,
        market_data: Dict,
        account_data: Dict,
    ) -> List[StrategyRecommendation]:
        """Generate signals from every enabled canonical strategy."""
        recommendations = []
        for strategy in ENABLED_STRATEGIES:
            rec = self.generate_signal(strategy, market_data, account_data)
            if rec:
                recommendations.append(rec)
        recommendations.sort(key=lambda x: x.confidence, reverse=True)
        return recommendations

    def _build_reasoning(self, strategy: str, signal: Any) -> str:
        regime = getattr(signal, "regime", None) or getattr(signal, "ml_regime", "n/a")
        conf = getattr(signal, "confidence", None) or getattr(signal, "ml_confidence", 0.0)
        if strategy == "QQQ_LEAPS":
            return (f"QQQ LEAPS canonical engine | regime={regime} | "
                    f"ml_confidence={conf:.2f} | gated pullback entry + PMCC overlay")
        return (f"TurboCore Pro v3.3 | regime={regime} | confidence={conf:.2f} | "
                f"hysteresis-tier allocation across QQQ/QLD/TQQQ/SGOV")

    def get_strategy_summary(self) -> Dict[str, Any]:
        """Get summary of the canonical strategy lineup."""
        return {
            "strategies": {
                "QQQ_LEAPS": {
                    "enabled": self.qqq_leaps_enabled,
                    "available": "QQQ_LEAPS" in self.generators,
                    "description": "Deep-ITM QQQ LEAPS calls after gated pullbacks + PMCC overlay",
                    "instrument": "QQQ options (LEAPS + short-dated calls)",
                    "engine": "src/qqq_leaps/canonical/qqq_leaps_enhanced_2y_hourly.py",
                    "requires_options_approval": True,
                },
                "TURBOCORE_PRO": {
                    "enabled": self.turbocore_pro_enabled,
                    "available": "TURBOCORE_PRO" in self.generators,
                    "description": "ETF-only regime allocator with drawdown control (v3.3)",
                    "instrument": "QQQ / QLD / TQQQ / SGOV",
                    "engine": "src/turbocore_pro (two-stage confidence pipeline)",
                    "requires_options_approval": False,
                },
            },
            "disabled_strategies": [
                "TQQQ", "TURBOBOUNCE", "ZEBRA", "THETA_SPRINT", "CALENDAR",
                "DIAGONAL_SPREAD", "VERTICAL_SPREAD", "OTM_NAKED", "SNDK",
                "DVO", "PMCC_STANDALONE", "DUAL_CORE", "EMA_CCI_MACD",
            ],
            "generators_loaded": list(self.generators.keys()),
        }
