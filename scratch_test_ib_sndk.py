import asyncio
import logging
import os
from dotenv import load_dotenv
from src.otm_naked.sndk.live.ib_connector import IBConnector
from src.otm_naked.sndk.live.market_data import SNDKMarketDataProvider
from src.otm_naked.sndk.live.option_chain_selector import LiveOptionSelector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    load_dotenv()
    
    ib_host = os.getenv("IB_HOST", "54.80.47.153")
    ib_port = int(os.getenv("IB_PORT", "4004"))
    
    ib_connector = IBConnector(host=ib_host, port=ib_port, client_id=102)
    
    if await ib_connector.connect_async():
        md = SNDKMarketDataProvider(ib_connector)
        
        logging.info("Testing SNDK spot price...")
        spot = await md.get_current_price("SNDK")
        logging.info(f"SNDK Spot Price: {spot}")
        
        logging.info("Testing Option Chains...")
        selector = LiveOptionSelector(md)
        opt_data = await selector.select_strike("SNDK", target_dte=21, target_delta=0.25, right="P")
        if opt_data:
            logging.info(f"Selected Option: {opt_data}")
        
        ib_connector.disconnect()
    else:
        logging.error("Failed to connect.")

if __name__ == "__main__":
    asyncio.run(main())
