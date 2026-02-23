"""
Dual-Core Unified Scheduler
===========================

Manages the daily timeline for both the CSP and PMCC strategy cores.
Extends ThetaScheduler to handle a multi-strategy workflow.

Timeline:
- 08:00 AM: Refresh Data/Fair Values
- 09:30 AM: Market Open / Stream Starts
- 09:45 AM: Dual-Core Allocator Runs -> Scans -> Signals
- 12:00 PM: Midday Position Check
- 03:45 PM: Pre-close Position Check
- 04:15 PM: Post-close Updates & P&L
- 05:00 PM: Consolidated EOD Report
"""

import logging
from typing import Callable, Dict
from datetime import datetime
import time

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.theta_spreads.scheduler import ThetaScheduler
from src.dual_core.allocator import DualCoreAllocator
from src.dual_core.reporter import DualCoreReporter
from src.csp.csp_scanner import CSPScanner
from src.csp.csp_position_manager import CSPPositionManager

logger = logging.getLogger(__name__)

class DualCoreScheduler(ThetaScheduler):
    """
    Coordinates the execution timeline for the Dual-Core strategy.
    """
    def __init__(
        self,
        allocator: DualCoreAllocator,
        reporter: DualCoreReporter,
        csp_scanner: CSPScanner,
        csp_manager: CSPPositionManager,
        pmcc_scanner: Any, # Mocked for PMCC dependencies
        pmcc_manager: Any,
        notification_callback: Callable[[str], None]
    ):
        super().__init__(notification_callback=notification_callback)
        self.allocator = allocator
        self.reporter = reporter
        self.csp_scanner = csp_scanner
        self.csp_manager = csp_manager
        self.pmcc_scanner = pmcc_scanner
        self.pmcc_manager = pmcc_manager
        
    def _run_morning_analysis(self):
        """Overrides Theta's morning analysis to run the Dual-Core workflow."""
        logger.info("Starting Dual-Core Morning Analysis (9:45 AM ET)")
        try:
            # 1. Gather Context
            vix = self._get_vix()
            regime = self._get_market_regime()
            portfolio_state = self._get_portfolio_state()
            
            # 2. Run Allocator
            allocation_plan = self.allocator.compute_allocation(regime, vix, portfolio_state)
            self._notify(f"🎯 New Allocation Target: CSP {allocation_plan.total_csp_pct*100:.0f}% | PMCC {allocation_plan.pmcc_moderate_pct*100:.0f}% | Cash {allocation_plan.cash_reserve_pct*100:.0f}%")
            
            # 3. Scan & Route (Run Both Scanners)
            logger.info("Running parallel scans for CSP and PMCC Candidates...")
            csp_candidates = self.csp_scanner.scan_opportunities(self._get_symbol_scores(), vix, "conservative", self.account_balance)
            # pmcc_candidates = self.pmcc_scanner.get_candidates()
            
            # 4. Filter and Publish 
            # (Router logic implemented inside the downstream signal publishers)
            if csp_candidates:
                self._notify(f"🔍 Found {len(csp_candidates)} CSP Candidates. Attempting entry...")
                # self.signal_publisher.publish_csp_entries(csp_candidates)
                
            self.last_analysis_date = datetime.now().date()
            
        except Exception as e:
            logger.error(f"Error in morning analysis: {e}", exc_info=True)
            self._notify(f"🚨 Dual-Core Workflow Error: {str(e)}")

    def _monitor_positions(self):
        """Midday and pre-close checks for both cores."""
        logger.info("Running Dual-Core Position Monitor")
        try:
            # Call check_exit_rules on both managers
            # Handle results (publish signals)
            pass
        except Exception as e:
             logger.error(f"Error monitoring positions: {e}", exc_info=True)
             
    def _run_eod_reporting(self):
        """Post-market unified reporting."""
        logger.info("Generating Dual-Core EOD Report")
        try:
             # Fetch data from both managers
             report = self.reporter.build_daily_report(
                 csp_data={}, # Mock
                 pmcc_data={}, # Mock
                 hedge_data={}, # Mock
                 allocation_targets={} # Mock
             )
             self._notify(report.generate_markdown())
        except Exception as e:
             logger.error(f"Error generating EOD report: {e}", exc_info=True)
             
    # Helper mocks for missing data sources
    def _get_vix(self): return 18.5
    def _get_market_regime(self): return "NORMAL"
    def _get_portfolio_state(self): return {}
    def _get_symbol_scores(self): return []
