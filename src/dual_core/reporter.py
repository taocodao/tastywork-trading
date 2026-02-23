"""
Dual-Core Consolidated Reporter
===============================

Aggregates P&L, Greeks, and metrics across both the CSP and PMCC strategies 
into a single unified dashboard view.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class DualCoreReport:
    timestamp: datetime
    total_net_liq: float
    total_buying_power_used: float
    
    # Strat break-down
    csp_net_liq: float
    csp_pnl: float
    pmcc_net_liq: float
    pmcc_pnl: float
    
    # Greeks
    portfolio_delta: float
    portfolio_theta: float
    portfolio_vega: float
    
    # Hedges
    tail_hedge_pnl: float
    
    # Allocation Drift
    current_allocation: Dict[str, float]
    target_allocation: Dict[str, float]
    
    def generate_markdown(self) -> str:
        """Formats the report as markdown for Telegram or logs."""
        return f"""## 📊 Dual-Core Portfolio Summary
**Time Tracking:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S ET')}
**Total Net Liq:** ${self.total_net_liq:,.2f}
**Buying Power Usage:** ${self.total_buying_power_used:,.2f} ({(self.total_buying_power_used/self.total_net_liq)*100:.1f}%)

### 📈 Core Performance
* **CSP Engine:** ${self.csp_net_liq:,.2f} | Day P&L: **${self.csp_pnl:+,.2f}**
* **PMCC Engine:** ${self.pmcc_net_liq:,.2f} | Day P&L: **${self.pmcc_pnl:+,.2f}**
* **Tail Hedges:** Day P&L: **${self.tail_hedge_pnl:+,.2f}**

### 📐 Portfolio Greeks
* **Δ Delta (Beta-Wtd):** {self.portfolio_delta:+.2f}
* **Θ Theta:** {self.portfolio_theta:+.2f}
* **V Vega:** {self.portfolio_vega:+.2f}

### ⚖️ Capital Allocation
* **CSP:** {self.current_allocation.get('csp', 0)*100:.1f}% (Target: {self.target_allocation.get('csp', 0)*100:.1f}%)
* **PMCC:** {self.current_allocation.get('pmcc', 0)*100:.1f}% (Target: {self.target_allocation.get('pmcc', 0)*100:.1f}%)
* **Cash:** {self.current_allocation.get('cash', 0)*100:.1f}% (Target: {self.target_allocation.get('cash', 0)*100:.1f}%)
"""

class DualCoreReporter:
    """Generates the unified reports."""
    def __init__(self):
        pass
        
    def build_daily_report(
        self, 
        csp_data: Dict, 
        pmcc_data: Dict, 
        hedge_data: Dict, 
        allocation_targets: Dict
    ) -> DualCoreReport:
        """
        Combines data from all sources into a single report object.
        """
        # Sum Net Liq
        csp_nlv = csp_data.get('net_liq', 0)
        pmcc_nlv = pmcc_data.get('net_liq', 0)
        cash_balance = csp_data.get('cash', 0) # Assuming passed in
        total_nlv = csp_nlv + pmcc_nlv + cash_balance + hedge_data.get('net_liq', 0)
        
        # Calculate current allocations
        curr_alloc = {
            'csp': csp_nlv / total_nlv if total_nlv > 0 else 0,
            'pmcc': pmcc_nlv / total_nlv if total_nlv > 0 else 0,
            'cash': cash_balance / total_nlv if total_nlv > 0 else 0
        }
        
        return DualCoreReport(
            timestamp=datetime.now(),
            total_net_liq=total_nlv,
            total_buying_power_used=csp_data.get('bp_used', 0) + pmcc_data.get('bp_used', 0),
            csp_net_liq=csp_nlv,
            csp_pnl=csp_data.get('day_pnl', 0),
            pmcc_net_liq=pmcc_nlv,
            pmcc_pnl=pmcc_data.get('day_pnl', 0),
            portfolio_delta=csp_data.get('delta', 0) + pmcc_data.get('delta', 0) + hedge_data.get('delta', 0),
            portfolio_theta=csp_data.get('theta', 0) + pmcc_data.get('theta', 0) + hedge_data.get('theta', 0),
            portfolio_vega=csp_data.get('vega', 0) + pmcc_data.get('vega', 0) + hedge_data.get('vega', 0),
            tail_hedge_pnl=hedge_data.get('day_pnl', 0),
            current_allocation=curr_alloc,
            target_allocation=allocation_targets
        )
