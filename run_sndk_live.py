#!/usr/bin/env python3
"""
SNDK Naked Options Bot — Main Entry Point (Persistent Process)
"""
import logging
import os
import time
from pathlib import Path

from src.otm_naked.sndk.config import SNDKLadderConfig
from src.otm_naked.sndk.live.ib_connector import IBConnector
from src.otm_naked.sndk.live.market_data import SNDKMarketDataProvider
from src.otm_naked.sndk.live.option_chain_selector import LiveOptionSelector
from src.otm_naked.sndk.live.order_executor import OrderExecutor
from src.otm_naked.sndk.live.risk_manager import LiveRiskManager
from src.otm_naked.sndk.live.state_manager import StateManager
from src.otm_naked.sndk.live.live_engine import LiveTradingEngine

# Setup logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/sndk_live.log")
    ]
)
logger = logging.getLogger("run_sndk_live")

def run_bot():
    from dotenv import load_dotenv
    load_dotenv()
    
    ib_host = os.getenv("IB_HOST", "127.0.0.1")
    ib_port = int(os.getenv("IB_PORT", 4004))
    client_id = int(os.getenv("IB_CLIENT_ID_ORDERS", 100))
    ticker = os.getenv("SNDK_TICKER", "SNDK")
    
    logger.info(f"Starting SNDK Intraday Bot. Connecting to {ib_host}:{ib_port}")
    
    # Initialize components
    config = SNDKLadderConfig()
    ib_connector = IBConnector(host=ib_host, port=ib_port, client_id=client_id)
    md_provider = SNDKMarketDataProvider(ib_connector)
    option_selector = LiveOptionSelector(md_provider)
    order_executor = OrderExecutor(ib_connector)
    risk_manager = LiveRiskManager(config)
    state_manager = StateManager(data_dir="data")
    
    engine = LiveTradingEngine(
        config=config,
        ib_connector=ib_connector,
        md_provider=md_provider,
        option_selector=option_selector,
        order_executor=order_executor,
        state_manager=state_manager,
        risk_manager=risk_manager
    )
    
    # Connect with retry logic
    if not ib_connector.connect():
        logger.error("Initial connection failed. Exiting.")
        return
        
    try:
        # Blocks and runs the intraday loop indefinitely
        engine.run_intraday_loop(ticker)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error in run loop: {e}", exc_info=True)
    finally:
        ib_connector.disconnect()

if __name__ == "__main__":
    # Give the gateway time to start up if running as a systemd service
    time.sleep(10)
    run_bot()
