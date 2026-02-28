import asyncio
import logging
import run_tqqq_scheduler
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)

async def test_scheduler_dry_run():
    print("=========================================")
    print(f"Starting TQQQ Scheduler Dry Run at {datetime.now()}")
    print("=========================================")
    
    # Force single-pass mode by disabling APScheduler flag
    run_tqqq_scheduler.SCHEDULER_AVAILABLE = False
    run_tqqq_scheduler.TQQQ_AUTO_TRADE = False
    
    # Optional: Mock TQQQ_RISK_LEVEL if you want to test a specific one
    # run_tqqq_scheduler.config.TQQQ_RISK_LEVEL = "Low"
    
    scheduler = run_tqqq_scheduler.TQQQScheduler(25000)
    
    print("\n--- Running Morning Refresh ---")
    await scheduler._morning_refresh()
    
    print("\n--- Running Entry Scan ---")
    await scheduler._scan_for_entry()
    
    print("\n--- Running Position Check (Should be empty initially) ---")
    await scheduler._position_check()
    
    print("\n--- Dry Run Complete ---")

if __name__ == "__main__":
    asyncio.run(test_scheduler_dry_run())
