import logging
import asyncio
from ib_insync import IB, util
import yaml
import os
from datetime import datetime, time

from src.otm_naked.sndk.live.ib_connector import IBConnector
from src.otm_naked.sndk.live.market_data import SNDKMarketDataProvider
from src.otm_naked.sndk.live.option_chain_selector import LiveOptionSelector
from src.otm_naked.sndk.live.strangle_manager_v41 import StrangleManagerV41

logger = logging.getLogger(__name__)

def load_config():
    path = os.path.join(os.path.dirname(__file__), '../config_v41.yaml')
    with open(path, 'r') as f:
        return yaml.safe_load(f)

class SNDKDDSBotV41:
    def __init__(self):
        self.config = load_config()
        self.ib_connector = IBConnector(
            host=self.config['ib']['host'],
            port=self.config['ib']['port'],
            client_id=self.config['ib']['client_id']
        )
        self.ib = self.ib_connector.get_ib()
        
        self.market_data = SNDKMarketDataProvider(self.ib_connector)
        self.chain_selector = LiveOptionSelector(self.market_data)
        
        self.manager = StrangleManagerV41(self.ib, self.config)
        self.ml_regime = "SIDEWAYS" # Default until ML model evaluates
        self.spot = 0.0

    def start(self):
        logger.info("Starting SNDK DDS Bot v4.1...")
        self.ib_connector.connect()
        
        # Sprint 7: Startup Reconciliation
        logger.info("Reconciling open positions and GTC brackets with IB...")
        self.manager.on_startup_reconcile()
        
        # Subscribe to market data updates (simplified for bot structure)
        self.market_data.subscribe_5min_bars('SNDK', self.on_5min_bar)
        
        # Run synchronous loop
        try:
            self.run_loop()
        except KeyboardInterrupt:
            logger.info("Bot shutting down...")
        finally:
            self.ib_connector.disconnect()

    def run_loop(self):
        """Run the main event loop continuously."""
        while self.ib.isConnected():
            now = datetime.now().time()
            
            # 1. Poll Market Data for 5-minute bars
            try:
                self.market_data.poll_5min_bars('SNDK')
            except Exception as e:
                logger.error(f"Error polling market data: {e}")
            
            # 2. EOD Cleanup at 15:45
            eod_time = time.fromisoformat(self.config['scheduler']['eod_cleanup'])
            if now.hour == eod_time.hour and now.minute == eod_time.minute:
                self.manager.eod_cleanup()
                
            # 3. Quarterly GTC resubmit check (runs once per day)
            if now.hour == 16 and now.minute == 5:
                self.manager.gtc_quarterly_resubmit_check()
                
            self.ib.sleep(60) # Wake up every minute to check time-based events

    def on_5min_bar(self, bars, has_new_bar):
        """Called every 5 minutes during market hours by market data provider."""
        if not has_new_bar or len(bars) == 0:
            return
            
        bar = bars[-1]
        
        now = datetime.now().time()
        market_open = time.fromisoformat(self.config['scheduler']['market_open'])
        market_close = time.fromisoformat(self.config['scheduler']['market_close'])
        
        if now < market_open or now >= market_close:
            return
            
        self.spot = bar.close
        logger.info(f"5-Min Bar: Spot={self.spot}")
        
        # 1. Run Management Loop (Combined PT, Rolls, Re-Legs)
        self.manager.run_management(
            spot=self.spot,
            ml_regime=self.ml_regime,
            vix=20.0, # Placeholder, should come from market_data
            spy_move=0.0, # Placeholder
            adx=25.0 # Placeholder
        )
        
        # 2. Check Entry Conditions
        # (This is simplified. In production, signals would come from ML entry gate)
        ivr = 40.0 # Placeholder from market_data
        
        # Phased Call Entry
        for sid, s in self.manager.strangles.items():
            if s.state == 'PENDING_CALL':
                days_open = (datetime.now() - s.opened_at).days if s.opened_at else 0
                if days_open <= self.config['phased_entry']['max_days_to_open_call']:
                    self.manager.open_call_leg(sid, self.spot, ivr, self.ml_regime)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot = SNDKDDSBotV41()
    bot.start() 
    print("Bot v4.1 initialized and started.")
