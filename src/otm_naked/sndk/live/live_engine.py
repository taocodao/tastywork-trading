import logging
import pandas as pd
import uuid
from datetime import datetime, time as dtime
import pytz

from src.otm_naked.sndk.live.state_manager import LivePosition
from src.otm_naked.sndk.feature_engineering import build_sndk_features

logger = logging.getLogger(__name__)

ET = pytz.timezone('America/New_York')

class LiveTradingEngine:
    """Main orchestrator for live trading (Intraday 5-min Loop)."""
    
    def __init__(self, config, ib_connector, md_provider, option_selector, order_executor, state_manager, risk_manager):
        self.config = config
        self.ib = ib_connector
        self.md = md_provider
        self.selector = option_selector
        self.executor = order_executor
        self.state = state_manager
        self.risk = risk_manager
        
        from src.otm_naked.sndk.signal_engine import SNDKLadderSignalEngine
        self.signal_engine = SNDKLadderSignalEngine(config)
        
        self.daily_features = None
        self.last_daily_refresh = None
        self.ticker = None
        
    def _is_market_hours(self):
        now_et = datetime.now(ET).time()
        return dtime(9, 30) <= now_et <= dtime(16, 0)
        
    def _refresh_daily_regime(self):
        """Fetches daily bars and computes ADX, Hurst, ROC5."""
        logger.info(f"Refreshing daily regime features for {self.ticker}...")
        df_bars = self.md.get_daily_bars(self.ticker, days=150)
        
        if df_bars.empty:
            logger.error("No daily bar data.")
            return
            
        vix_series = self.md.get_vix_history(days=150)
        # Assuming we don't have SPY history built yet, just pass dummy for now
        
        df_features = build_sndk_features(
            close=df_bars['close'],
            open_price=df_bars['open'],
            high=df_bars['high'],
            low=df_bars['low'],
            volume=df_bars['volume'],
            vix=vix_series
        )
        
        if df_features.empty:
            logger.error("Feature building failed.")
            return
            
        self.daily_features = df_features.iloc[-1].to_dict()
        self.last_daily_refresh = datetime.now().date()
        logger.info(f"Regime Refreshed: {self.daily_features.get('regime')}, IVR {self.daily_features.get('ivr'):.1f}")

    def run_intraday_loop(self, ticker: str):
        """Main persistent loop for market hours."""
        self.ticker = ticker
        logger.info(f"Starting intraday loop for {ticker}")
        
        # 1. Startup: compute daily regime features
        self._refresh_daily_regime()
        
        # 2. Subscribe to live 5-min bars
        self.md.subscribe_5min_bars(ticker, callback=self._on_new_bar)
        
        # 3. Main loop: ib.sleep() until market close
        while True:
            try:
                if not self._is_market_hours():
                    self.ib.get_ib().sleep(60)
                    
                    # Force a regime refresh at midnight/open
                    if self.last_daily_refresh and datetime.now().date() > self.last_daily_refresh:
                        if self.ib.is_connected():
                            self._refresh_daily_regime()
                    continue
                    
                # If we were disconnected and just reconnected
                if self.ib.needs_reconnect:
                    logger.info("Reconnect flag detected. Re-subscribing to market data...")
                    self.md.unsubscribe_5min_bars()
                    self.ib.get_ib().sleep(5)
                    self.md.subscribe_5min_bars(ticker, callback=self._on_new_bar)
                    self.ib.needs_reconnect = False
                    
                self.ib.get_ib().sleep(30)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                self.ib.get_ib().sleep(10)
                
    def _on_new_bar(self, bars, has_new_bar):
        """Fires every 5 minutes when a new bar closes."""
        if not has_new_bar:
            return
            
        logger.info("New 5-min bar detected. Evaluating signals...")
        try:
            intraday_move = self.md.get_intraday_move(self.ticker)
            self._evaluate_and_trade(intraday_move)
        except Exception as e:
            logger.error(f"Error evaluating signals: {e}", exc_info=True)
            
    def _evaluate_and_trade(self, intraday_move: float):
        if not self.daily_features:
            return
            
        spot = self.md.get_current_price(self.ticker)
        if spot <= 0:
            return
            
        # 1. Manage existing positions
        self._manage_positions(spot)
        
        # 2. Evaluate entry signal
        open_calls = len([p for p in self.state.get_positions() if p.opt_type == "call"])
        open_puts = len([p for p in self.state.get_positions() if p.opt_type == "put"])
        
        # Inject intraday move into the daily features for the signal engine
        current_features = self.daily_features.copy()
        current_features['daily_move_pct'] = intraday_move
        
        row_series = pd.Series(current_features)
        signal = self.signal_engine.evaluate(row_series, open_calls, open_puts)
        
        if not signal.should_enter:
            return
            
        logger.info(f"Entry Signal Fired: {signal.direction.upper()} (Move: {intraday_move:.2f}%)")
        
        # Check Risk
        nav = self.executor.get_net_liquidation()
        earnings_days = current_features.get('earnings_days_away', 999)
        
        if not self.risk.is_safe_to_enter(nav, self.state.get_positions(), signal.direction, earnings_days):
            return
            
        # 3. Select Option Strike
        regime = str(current_features.get("regime", "SIDEWAYS"))
        base_delta = getattr(self.config, 'delta_trending', 0.15) if regime in ("UPTREND", "DOWNTREND", "EXTREME_UPTREND", "EXTREME_DOWNTREND") else self.config.initial_delta
        
        opt_data = self.selector.select_strike(
            ticker=self.ticker,
            target_dte=signal.target_dte,
            target_delta=base_delta,
            right="C" if signal.direction == "call" else "P"
        )
        
        if not opt_data:
            logger.error("Failed to select option strike.")
            return
            
        contract = opt_data["contract"]
        iv = opt_data["iv"]
        
        # 4. Execute STO
        max_risk = nav * self.config.position_size_pct
        margin_req = contract.strike * 100 * 0.20
        contracts = max(1, int(max_risk / margin_req))
        
        limit_price = opt_data["mid"] if opt_data["mid"] > 0 else opt_data["ask"]
        if limit_price <= 0.05:
            logger.info(f"Premium too low ({limit_price}), skipping.")
            return
            
        trade = self.executor.sell_to_open(contract, contracts, limit_price, available_funds=self.executor.get_buying_power())
        
        if trade and trade.orderStatus.status == 'Filled':
            fill_price = trade.orderStatus.avgFillPrice
            pos = LivePosition(
                id=str(uuid.uuid4()),
                symbol=self.ticker,
                opt_type=signal.direction,
                strike=contract.strike,
                expiry=contract.lastTradeDateOrContractMonth,
                entry_premium=fill_price,
                entry_delta=opt_data["delta"],
                entry_iv=iv,
                entry_date=datetime.now().isoformat(),
                contracts=trade.orderStatus.filled,
                target_dte=signal.target_dte
            )
            self.state.add_position(pos)
            logger.info(f"Successfully entered new rung: {pos}")

    def _manage_positions(self, spot: float):
        """Checks profit/stops and closes positions."""
        from ib_insync import Option
        
        positions = self.state.get_positions()
        
        if not positions:
            return
            
        # Build list of contracts to fetch Greeks for
        contracts = []
        for pos in positions:
            opt = Option(pos.symbol, pos.expiry, pos.strike, "C" if pos.opt_type == "call" else "P", 'SMART', currency='USD', tradingClass=pos.symbol)
            contracts.append(opt)
            
        # Batch fetch
        greeks_data = self.md.get_contract_greeks_and_prices(contracts)
        
        for pos, contract in zip(positions, contracts):
            if contract.conId not in greeks_data:
                continue
                
            opt_data = greeks_data[contract.conId]
            current_prem = opt_data["mid"] if opt_data["mid"] > 0 else opt_data["ask"]
            if current_prem <= 0:
                continue
                
            entry_date = datetime.fromisoformat(pos.entry_date).date()
            days_held = (datetime.now().date() - entry_date).days
            T_rem = max(pos.target_dte - days_held, 1)
            
            pnl_pct = (pos.entry_premium - current_prem) / pos.entry_premium
            
            effective_target = self.config.profit_take_pct
            if pos.target_dte <= getattr(self.config, 'profit_dte_threshold', 25):
                effective_target = getattr(self.config, 'profit_take_pct_short', 0.25)
                
            should_close = False
            reason = ""
            
            if pnl_pct >= effective_target:
                should_close = True
                reason = "Profit Target"
            elif pnl_pct <= -self.config.stop_loss_credit_mult:
                should_close = True
                reason = "Stop Loss"
            elif T_rem <= self.config.dte_roll_threshold:
                should_close = True
                reason = "DTE Threshold"
                
            if should_close:
                logger.info(f"Closing position {pos.strike} {pos.opt_type}: {reason} (PnL: {pnl_pct*100:.1f}%)")
                limit_price = opt_data["ask"] if opt_data["ask"] > 0 else opt_data["mid"] + 0.10
                
                trade = self.executor.buy_to_close(contract, pos.contracts, limit_price)
                if trade and trade.orderStatus.status == 'Filled':
                    exit_price = trade.orderStatus.avgFillPrice
                    realized = (pos.entry_premium - exit_price) * pos.contracts * 100
                    self.risk.record_pnl(realized)
                    self.state.remove_position(pos.id, exit_price, reason)
