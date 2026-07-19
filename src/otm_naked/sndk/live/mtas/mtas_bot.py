"""
MTAS (Momentum-Triggered Asymmetric Strangle Ladder) live bot entrypoint.

Distinct from ../bot_v41.py (SNDK DDS Bot v4.1 -- delta-targeted, 3-strangle cap, ML
regime gating, premium-multiple stop-loss). This bot runs the strategy that was
walk-forward validated this session in real_rule_backtest_5m.py. See config_mtas.yaml
for the full parameter set and validation summary.

DO NOT run this alongside bot_v41.py against the same live trading account -- they would
both try to trade SNDK options independently and could double up on margin/positions.
They may safely run against the SAME paper account only if you want a side-by-side
comparison; use different client_ids (already set in config_mtas.yaml: 141 vs 102).

Usage:
    python -m src.otm_naked.sndk.live.mtas.mtas_bot
"""
import logging
import os
import time
import yaml

from src.otm_naked.sndk.live.ib_connector import IBConnector
from src.otm_naked.sndk.live.market_data import SNDKMarketDataProvider
from src.otm_naked.sndk.live.option_chain_selector import LiveOptionSelector
from src.otm_naked.sndk.live.order_executor import OrderExecutor
from .mtas_state import MTASStateManager
from .mtas_ladder_manager import MTASLadderManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def load_config() -> dict:
    path = os.path.join(os.path.dirname(__file__), "config_mtas.yaml")
    with open(path, "r") as f:
        return yaml.safe_load(f)


class MTASBot:
    def __init__(self):
        self.config = load_config()
        if self.config.get("mode") == "live":
            logger.warning(
                "config_mtas.yaml has mode='live'. This module has NOT been run against a "
                "live IB connection yet -- only walk-forward backtested. Strongly recommend "
                "paper-trading first. Proceeding anyway per config."
            )

        self.ib_connector = IBConnector(
            host=self.config["ib"]["host"],
            port=self.config["ib"]["port"],
            client_id=self.config["ib"]["client_id"],
        )
        self.ib = self.ib_connector.get_ib()
        self.market_data = SNDKMarketDataProvider(self.ib_connector)
        self.selector = LiveOptionSelector(self.market_data)
        self.executor = OrderExecutor(self.ib_connector)
        self.state = MTASStateManager(data_dir=self.config.get("data_dir", "data_mtas"))
        self.manager = MTASLadderManager(
            ib=self.ib,
            config=self.config,
            market_data=self.market_data,
            option_selector=self.selector,
            order_executor=self.executor,
            state_manager=self.state,
        )
        self.ticker = self.config["ticker"]

    def start(self):
        logger.info(f"Starting MTAS ladder bot for {self.ticker} (mode={self.config.get('mode')})...")
        self.ib_connector.connect()
        self.market_data.subscribe_5min_bars(self.ticker, lambda bars, has_new: None)
        try:
            self.run_loop()
        except KeyboardInterrupt:
            logger.info("MTAS bot shutting down...")
        finally:
            self.ib_connector.disconnect()

    def run_loop(self):
        interval = self.config.get("management_interval_seconds", 60)
        while self.ib.isConnected():
            try:
                self.market_data.poll_5min_bars(self.ticker)
                self.manager.on_management_tick()
            except Exception as e:
                logger.exception(f"Error in MTAS management tick: {e}")
            self.ib.sleep(interval)


if __name__ == "__main__":
    MTASBot().start()
