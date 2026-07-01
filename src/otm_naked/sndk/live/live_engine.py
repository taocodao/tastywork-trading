import logging
import asyncio
from datetime import datetime
import pandas as pd
import uuid

from src.otm_naked.sndk.live.state_manager import LivePosition

logger = logging.getLogger(__name__)

class LiveTradingEngine:
    """Main orchestrator for live trading."""
    
    def __init__(self, config, ib_connector, md_provider, option_selector, order_executor, state_manager, risk_manager):
        self.config = config
        self.ib = ib_connector
        self.md = md_provider
        self.selector = option_selector
        self.executor = order_executor
        self.state = state_manager
        self.risk = risk_manager
        
        # We reuse the backtest signal engine logic, but feed it live data
        from src.otm_naked.sndk.signal_engine import SNDKLadderSignalEngine
        self.signal_engine = SNDKLadderSignalEngine(config)
        
    async def run_daily_cycle(self, ticker: str):
        """Executes the end-of-day trading cycle (runs around 3:55 PM)."""
        logger.info(f"Starting live daily cycle for {ticker}")
        
        if not self.ib.is_connected():
            if not await self.ib.connect_async():
                logger.error("Cannot run cycle: IB disconnected.")
                return
                
        try:
            # 1. Fetch live features
            df_bars = await self.md.get_daily_bars(ticker, days=150)
            if df_bars.empty:
                logger.error("No bar data, aborting cycle.")
                return
                
            spot = await self.md.get_current_price(ticker)
            if spot <= 0:
                logger.error("Invalid spot price, aborting cycle.")
                return
                
            from src.otm_naked.sndk.feature_engineering import build_sndk_features
            # Need vix
            vix = await self.md.get_vix_close()
            vix_series = pd.Series([vix]*len(df_bars), index=df_bars.index)
            
            # Construct features
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
                
            latest_row = df_features.iloc[-1].to_dict()
            latest_date = df_features.index[-1]
            logger.info(f"Features: Move {latest_row['daily_move_pct']:.2f}%, Regime {latest_row['regime']}, IVR {latest_row['ivr']:.1f}")
            
            # 2. Manage existing positions
            await self._manage_positions(spot, latest_date)
            
            # 3. Evaluate entry signal
            open_calls = len([p for p in self.state.get_positions() if p.opt_type == 'call'])
            open_puts = len([p for p in self.state.get_positions() if p.opt_type == 'put'])
            
            # Signal check
            # Convert series row to dict/series expected by signal_engine
            row_series = pd.Series(latest_row)
            signal = self.signal_engine.evaluate(row_series, open_calls, open_puts)
            
            if not signal.should_enter:
                logger.info(f"No entry signal: {signal.reason}")
                return
                
            # Check Risk
            bp = await self.executor.get_buying_power()
            nav = bp * 2.0 # Approximation of Net Liq, could query explicitly
            if not self.risk.is_safe_to_enter(nav, self.state.get_positions(), signal.direction):
                return
                
            # 4. Select Option Strike
            regime = str(latest_row.get("regime", "SIDEWAYS"))
            base_delta = getattr(self.config, 'delta_trending', 0.15) if regime in ("UPTREND", "DOWNTREND", "EXTREME_UPTREND", "EXTREME_DOWNTREND") else self.config.initial_delta
            
            opt_data = await self.selector.select_strike(
                ticker=ticker,
                target_dte=signal.target_dte,
                target_delta=base_delta,
                right="C" if signal.direction == "call" else "P"
            )
            
            if not opt_data:
                logger.error("Failed to select option strike.")
                return
                
            contract = opt_data["contract"]
            iv = opt_data["iv"]
            
            # 5. Execute STO
            # Sizing
            max_risk = nav * self.config.position_size_pct
            margin_req = contract.strike * 100 * 0.20
            contracts = max(1, int(max_risk / margin_req))
            
            # Use mid price for limit
            limit_price = (opt_data["bid"] + opt_data["ask"]) / 2
            if limit_price <= 0.05:
                logger.info(f"Premium too low ({limit_price}), skipping.")
                return
                
            trade = await self.executor.sell_to_open(contract, contracts, limit_price)
            
            if trade.orderStatus.status == 'Filled':
                fill_price = trade.orderStatus.avgFillPrice
                pos = LivePosition(
                    id=str(uuid.uuid4()),
                    symbol=ticker,
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
                
        except Exception as e:
            logger.error(f"Error in daily cycle: {e}")
            
    async def _manage_positions(self, spot: float, today_date: datetime):
        """Checks profit/stops and closes positions."""
        from ib_insync import Option
        
        positions = self.state.get_positions()
        to_remove = []
        
        for pos in positions:
            # Query current price
            contract = Option(pos.symbol, pos.expiry, pos.strike, "C" if pos.opt_type == "call" else "P", "SMART")
            opt_data = await self.md.get_contract_greeks_and_prices(contract)
            
            current_prem = opt_data["mid"] if opt_data["mid"] > 0 else opt_data["ask"]
            if current_prem <= 0:
                continue
                
            entry_date = datetime.fromisoformat(pos.entry_date).date()
            days_held = (datetime.now().date() - entry_date).days
            T_rem = max(pos.target_dte - days_held, 1)
            
            pnl_pct = (pos.entry_premium - current_prem) / pos.entry_premium
            
            # Profit target check
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
                # Add a bit to mid price to ensure fill on exit
                limit_price = opt_data["ask"] 
                trade = await self.executor.buy_to_close(contract, pos.contracts, limit_price)
                if trade.orderStatus.status == 'Filled':
                    to_remove.append(pos.id)
                    realized = (pos.entry_premium - trade.orderStatus.avgFillPrice) * pos.contracts * 100
                    self.risk.record_pnl(realized)
                    
        for pid in to_remove:
            self.state.remove_position(pid)
