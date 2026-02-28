import asyncio, logging
from run_tqqq_scheduler import TQQQScheduler

logging.basicConfig(level=logging.INFO)

async def test_scheduler():
    scheduler = TQQQScheduler(account_value=25000)
    
    print('\n--- Running Morning Refresh (Status Generation) ---')
    await scheduler._morning_refresh()
    
    print('\n--- Running Entry Scan (Theta + Swing Layers) ---')
    await scheduler._scan_for_entry()
    
    print('\n--- Running Position Check ---')
    await scheduler._position_check()
    
    print('\n--- Running EOD Report ---')
    await scheduler._eod_report()
    
if __name__ == '__main__':
    asyncio.run(test_scheduler())
