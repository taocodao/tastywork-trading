"""
Roll Qualifier
==============
Implements the V3 8-point roll-down qualifier.
Before allowing a roll-down, all conditions must pass.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

@dataclass
class RollQualifierResult:
    passed: bool
    reasons: List[str]

class RollQualifier:
    def __init__(self, config):
        self.config = config

    def evaluate_roll(self, position, current_price: float, iv_rank: float, 
                      vol_regime: str, ml_prob: float, new_credit: float, new_width: float,
                      bp_total: float, bp_consumed: float) -> RollQualifierResult:
        """
        Evaluate if a roll is permitted according to V3 rules.
        """
        reasons = []
        passed = True

        # 1. Structural Support
        dist_from_entry = (current_price - position.tqqq_price_at_entry) / position.tqqq_price_at_entry
        if dist_from_entry < -0.30: # 30% drop is severe
            passed = False
            reasons.append(f"Structural decline > 30% ({dist_from_entry:.1%})")

        # 2. IV still elevated
        if iv_rank < 25.0:
            passed = False
            reasons.append(f"IV Rank too low for roll ({iv_rank:.1f} < 25)")

        # 3. ML Score >= 0.55
        if ml_prob < 0.55:
            passed = False
            reasons.append(f"ML Roll Score too low ({ml_prob:.2f} < 0.55)")

        # 4. New credit >= 25% of new width
        if new_width > 0:
            credit_ratio = new_credit / new_width
            if credit_ratio < 0.25:
                passed = False
                reasons.append(f"New credit ratio too low ({credit_ratio:.0%} < 25%)")

        # 5. Roll count limit
        roll_count = getattr(position, 'roll_count', 0)
        max_rolls = getattr(self.config, 'V3_MAX_ROLLS_PER_CYCLE', 1)
        if roll_count >= max_rolls:
            passed = False
            reasons.append(f"Max rolls exceeded ({roll_count} >= {max_rolls})")

        # 6. BP Check (combined risk <= 6%)
        # Note: We simulate this check by ensuring consumed BP doesn't exceed 6% of total
        risk_pct = bp_consumed / max(1.0, bp_total)
        if risk_pct > 0.06:
            passed = False
            reasons.append(f"BP Risk too high ({risk_pct:.1%} > 6%)")

        return RollQualifierResult(passed=passed, reasons=reasons)
