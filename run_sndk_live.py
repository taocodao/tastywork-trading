import os
import asyncio
import logging
from dotenv import load_dotenv

from src.otm_naked.sndk.config import SNDKLadderConfig
from src.otm_naked.sndk.live.ib_connector import IBConnector
from src.otm_naked.sndk.live.market_data import SNDKMarketDataProvider
from src.otm_naked.sndk.live.option_chain_selector import LiveOptionSelector
from src.otm_naked.sndk.live.order_executor import OrderExecutor
from src.otm_naked.sndk.live.state_manager import StateManager
from src.otm_naked.sndk.live.risk_manager import LiveRiskManager
from src.otm_naked.sndk.live.live_engine import LiveTradingEngine

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    load_dotenv()
    
    # 1. Config Setup
    ticker = os.getenv("SNDK_TICKER", "SNDK")
    config = SNDKLadderConfig(universe=[ticker])
    # Perplexity High Frequency Config (V3)
    config.entry_trigger_pct = 0.5
    config.ivr_min = 20.0
    config.position_size_pct = 0.10
    config.profit_take_pct = 0.40
    config.profit_take_pct_short = 0.25
    
    # 2. Components
    ib_host = os.getenv("IB_HOST", "127.0.0.1")
    ib_port = int(os.getenv("IB_PORT", "4002"))
    
    ib_connector = IBConnector(host=ib_host, port=ib_port, client_id=100)
    market_data = SNDKMarketDataProvider(ib_connector)
    option_selector = LiveOptionSelector(market_data)
    order_executor = OrderExecutor(ib_connector)
    state_manager = StateManager()
    risk_manager = LiveRiskManager(config)
    
    # 3. Engine
    engine = LiveTradingEngine(
        config=config,
        ib_connector=ib_connector,
        md_provider=market_data,
        option_selector=option_selector,
        order_executor=order_executor,
        state_manager=state_manager,
        risk_manager=risk_manager
    )
    
    # 4. Run Cycle
    await engine.run_daily_cycle(ticker)
    
    # Cleanup
    ib_connector.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
