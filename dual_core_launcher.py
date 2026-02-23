"""
Dual-Core Launcher
==================

Bootstraps the entire Dual-Core Options Alpha strategy.
Initializes the CSP engine, PMCC engine, and the Dual-Core Orchestrator.
"""

import logging
import sys
import os
import time
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- Core Dependencies ---
from src.dual_core.allocator import DualCoreAllocator
from src.dual_core.reporter import DualCoreReporter
from src.dual_core.scheduler import DualCoreScheduler
from src.dual_core.unified_risk import UnifiedRiskManager

# --- CSP Core ---
from src.csp.csp_scanner import CSPScanner
from src.csp.csp_position_manager import CSPPositionManager

# --- PMCC Core ---
from src.pmcc.pmcc_screener import PMCCScreener
from src.pmcc.pmcc_stop_manager import PMCCStopManager

# --- Mock ML Imports (Will be replaced in Phase 4) ---
# from src.dual_core.ml.allocation_rl_agent import AllocationRLAgent
# from src.dual_core.ml.iv_switch_router import IVSwitchRouter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DualCoreLauncher")

def telegram_notify(message: str):
    logger.info(f"[TELEGRAM MOCK] {message}")

def launch_dual_core():
    logger.info("==============================================")
    logger.info("🚀 Launching Dual-Core Options Alpha Strategy 🚀")
    logger.info("==============================================")
    
    # 1. Initialize Cross-Core Risk
    logger.info("1. Initializing Unified Risk Manager...")
    risk_manager = UnifiedRiskManager(account_size=100000.0)
    
    # 2. Initialize CSP Engine (Core 1)
    logger.info("2. Initializing CSP Income Engine...")
    csp_scanner = CSPScanner()
    csp_manager = CSPPositionManager(total_capital=40000.0) # Assume 40% base start
    
    # 3. Initialize PMCC Engine (Core 2)
    logger.info("3. Initializing LEAPS Growth Engine (PMCC)...")
    pmcc_scanner = PMCCScreener()
    pmcc_manager = PMCCStopManager()
    
    # 4. Initialize ML Components (Placeholder for Phase 4)
    logger.info("4. Initializing Intelligence Layer...")
    # rl_agent = AllocationRLAgent.load("models/allocation_ppo.zip")
    # iv_router = IVSwitchRouter(...)
    
    # 5. Initialize Orchestrator
    logger.info("5. Bootstrapping Dual-Core Orchestrator...")
    allocator = DualCoreAllocator(rl_agent=None, iv_router=None) # ML injection goes here
    reporter = DualCoreReporter()
    
    scheduler = DualCoreScheduler(
        allocator=allocator,
        reporter=reporter,
        csp_scanner=csp_scanner,
        csp_manager=csp_manager,
        pmcc_scanner=pmcc_scanner,
        pmcc_manager=pmcc_manager,
        notification_callback=telegram_notify
    )
    
    logger.info("✅ Initialization Complete. Entering Daily Schedule Loop.")
    telegram_notify("🚀 Dual-Core Options Alpha system is online.")
    
    # Main run loop
    try:
        scheduler.run()
    except KeyboardInterrupt:
        logger.info("\nShutting down Dual-Core system safely.")
        sys.exit(0)

if __name__ == "__main__":
    launch_dual_core()
