from ib_insync import IB, Option, util
import pandas as pd
import logging
import asyncio

async def test_ib_historical_option():
    ib = IB()
    try:
        await ib.connectAsync('34.203.194.137', 4004, clientId=999)
        print("Connected to IB Gateway")
        
        # Try to define an option that expired recently
        contract = Option('SNDK', '20260619', 2000, 'C', 'SMART', 'USD')
        
        print("Qualifying contract...")
        qualified = await ib.qualifyContractsAsync(contract)
        if not qualified:
            print("Could not qualify contract.")
            return
            
        print(f"Qualified: {qualified[0]}")
        
        print("Requesting historical data...")
        bars = await ib.reqHistoricalDataAsync(
            qualified[0],
            endDateTime='',
            durationStr='10 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True
        )
        
        if bars:
            df = util.df(bars)
            print(df)
        else:
            print("No historical data returned.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    asyncio.run(test_ib_historical_option())
