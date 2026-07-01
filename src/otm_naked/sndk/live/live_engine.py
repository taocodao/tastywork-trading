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
        self.risk.reset_daily_stats()
        df_bars = self.md.get_daily_bars(self.ticker, days=150)
        
        if df_bars.empty:
            logger.error("No daily bar data.")
            return
            
        vix_series = self.md.get_vix_history(days=150)
        spy_bars = self.md.get_daily_bars('SPY', days=150)
        spy_close = spy_bars['close'] if not spy_bars.empty else None
        
        df_features = build_sndk_features(
            close=df_bars['close'],
            open_price=df_bars['open'],
            high=df_bars['high'],
            low=df_bars['low'],
            volume=df_bars['volume'],
            vix=vix_series,
            spy_close=spy_close
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
        self.risk.peak_nav = self.executor.get_net_liquidation()
        
        # 2. Subscribe to live 5-min bars
        self.md.subscribe_5min_bars(ticker, callback=self._on_new_bar)
        
        # 3. Main loop: ib.sleep() until market close
        last_poll_time = datetime.min
        last_margin_check = datetime.min
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
                    self.ib.connect()
                    self.md.unsubscribe_5min_bars()
                    self.ib.get_ib().sleep(5)
                    self.md.subscribe_5min_bars(ticker, callback=self._on_new_bar)
                    self.ib.needs_reconnect = False
                    
                now = datetime.now()
                
                # V3 Margin Check every 30s
                if (now - last_margin_check).total_seconds() >= 30:
                    el = self.executor.get_excess_liquidity()
                    nav = self.executor.get_net_liquidation()
                    health = self.risk.check_margin_health(el, nav, self.state.get_positions())
                    if health == "CRITICAL":
                        logger.critical("Margin health CRITICAL outside of bar update. Triggering emergency close logic.")
                        spot = self.md.get_current_price(self.ticker)
                        self._manage_positions(spot)
                    last_margin_check = now
                
                # 60s bar poll logic (for fallback to delayed data if needed)
                if (now - last_poll_time).total_seconds() >= 60:
                    self.md.poll_5min_bars(ticker)
                    last_poll_time = now
                    
                self.ib.get_ib().sleep(5)
                
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
            
        # 1. Manage existing positions (Closes happen first)
        self._manage_positions(spot)
        
        # 2. Evaluate entry signal
        # Inject intraday move into the daily features for the signal engine
        current_features = self.daily_features.copy()
        current_features['daily_move_pct'] = intraday_move
        
        row_series = pd.Series(current_features)
        
        eval_result = self.signal_engine.evaluate(row_series, self.state.get_positions())
        logger.info(f"DDS Evaluation - State: {eval_result.state} | Score: {eval_result.dss_score:.2f}")
        
        if not eval_result.actions:
            return
            
        # Check Risk
        nav = self.executor.get_net_liquidation()
        el = self.executor.get_excess_liquidity()
        regime = str(current_features.get("regime", "SIDEWAYS"))
        
        for action in eval_result.actions:
            if action.action == "SELL_TO_OPEN":
                logger.info(f"Attempting STO {action.side.upper()}: {action.reason}")
                
                iv_annual = current_features.get("iv_est", 0.60) # fallback to 60% if missing
                
                # Use RiskManager V3 entry gate
                allowed, block_reason = self.risk.can_add_rung(
                    side=action.side,
                    sndk_price=spot,
                    iv=iv_annual,
                    regime=regime,
                    nav=nav,
                    excess_liquidity=el,
                    positions=self.state.get_positions()
                )
                
                if not allowed:
                    logger.info(f"Trade blocked by Risk Manager: {block_reason}")
                    continue
                    
                # 3. Select Option Strike
                opt_data = self.selector.select_strike(
                    ticker=self.ticker,
                    target_dte=action.target_dte,
                    target_delta=action.target_delta,
                    right="C" if action.side == "call" else "P"
                )
                
                if not opt_data:
                    logger.error(f"Failed to select option strike for {action.side}.")
                    continue
                    
                contract = opt_data["contract"]
                iv = opt_data["iv"]
                
                # 4. Execute STO
                # In V3, quantity is 1 contract by default for scaling in
                contracts = action.quantity
                
                limit_price = opt_data["mid"] if opt_data["mid"] > 0 else opt_data["ask"]
                if limit_price <= 0.05:
                    logger.info(f"Premium too low ({limit_price}), skipping.")
                    continue
                    
                trade = self.executor.sell_to_open(contract, contracts, limit_price, available_funds=self.executor.get_buying_power())
                
                if trade and trade.orderStatus.status == 'Filled':
                    fill_price = trade.orderStatus.avgFillPrice
                    
                    rung_id = len(self.state.get_positions()) + 1
                    
                    pos = LivePosition(
                        id=str(uuid.uuid4()),
                        symbol=self.ticker,
                        opt_type=action.side,
                        strike=contract.strike,
                        expiry=contract.lastTradeDateOrContractMonth,
                        entry_premium=fill_price,
                        entry_underlying_price=spot,
                        entry_delta=opt_data["delta"],
                        entry_iv=iv,
                        entry_date=datetime.now().isoformat(),
                        contracts=trade.orderStatus.filled,
                        target_dte=action.target_dte,
                        rung_id=rung_id
                    )
                    self.state.add_position(pos)
                    logger.info(f"Successfully entered new rung: {pos}")
                    
                    # Deduct margin from EL for subsequent actions in the loop
                    el -= self.risk.margin_per_contract

    def _manage_positions(self, spot: float):
        """Checks profit/stops and closes positions using V3 Risk Manager."""
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
        
        # Build current_option_prices dict for RiskManager
        current_option_prices = {}
        for pos, contract in zip(positions, contracts):
            matched_data = None
            if contract.conId in greeks_data:
                matched_data = greeks_data[contract.conId]
            else:
                for cid, data in greeks_data.items():
                    if data.get("strike") == contract.strike and data.get("right") == contract.right:
                        matched_data = data
                        break
                        
            if matched_data:
                current_prem = matched_data["mid"] if matched_data["mid"] > 0 else matched_data["ask"]
                key = f"{pos.strike}_{pos.opt_type}"
                current_option_prices[key] = current_prem

        el = self.executor.get_excess_liquidity()
        
        to_close = self.risk.rungs_to_close(spot, current_option_prices, el, positions)
        
        for pos, reason in to_close:
            logger.info(f"Closing position {pos.strike} {pos.opt_type}: {reason}")
            
            # Find the option data to get a limit price
            key = f"{pos.strike}_{pos.opt_type}"
            current_prem = current_option_prices.get(key, 0.0)
            limit_price = current_prem + 0.05 if current_prem > 0 else 0.0
            
            # If it's an emergency close, maybe we don't even use a limit, but executor only has limit order right now
            # So just use a generous limit
            if "EMERGENCY" in reason:
                limit_price = current_prem * 1.20 + 0.50  # Pay up to get out
                
            if limit_price <= 0:
                logger.warning(f"Could not determine exit price for {pos.strike} {pos.opt_type}")
                continue

            contract_obj = Option(pos.symbol, pos.expiry, pos.strike, "C" if pos.opt_type == "call" else "P", 'SMART', currency='USD', tradingClass=pos.symbol)
            trade = self.executor.buy_to_close(contract_obj, pos.contracts, limit_price)
            if trade and trade.orderStatus.status == 'Filled':
                exit_price = trade.orderStatus.avgFillPrice
                realized = (pos.entry_premium - exit_price) * pos.contracts * 100
                self.risk.record_pnl(realized)
                self.state.remove_position(pos.id, exit_price, reason)
