import asyncio
import logging
import traceback
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

def run_it():
    try:
        asyncio.run(test_scheduler())
        with open('test_error.log', 'w') as f:
            f.write("SUCCESS")
    except Exception as e:
        with open('test_error.log', 'w') as f:
            f.write("EXCEPTION CAUGHT:\n")
            f.write(traceback.format_exc())

if __name__ == '__main__':
    run_it()
