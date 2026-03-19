"""
Long Put Replacer
=================
Automates the long put replacement cycle described in V3.
Triggered when long put DTE <= 7 and short put DTE > 21.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class LongPutReplacer:
    def __init__(self, config):
        self.config = config

    def should_replace(self, position, current_date, short_dte: int, long_dte: int) -> bool:
        """
        Check if we need to replace the long put.
        """
        if long_dte <= getattr(self.config, 'V3_LAW1_HEDGE_REPLACE_DTE', 7):
            if short_dte > 21:
                return True
        return False

    def get_replacement_params(self, regime: str) -> Dict[str, Any]:
        """
        Return the parameters for the new long put.
        """
        params = self.config.TQQQ_DIAGONAL_PARAMS.get(regime, self.config.TQQQ_DIAGONAL_PARAMS['NORMAL'])
        return {
            'target_dte': params['hedge_dte'],
            'target_delta': params['hedge_delta']
        }
