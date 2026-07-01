"""
SNDK Dynamic Ladder Strategy - Walk-Forward Backtest Engine
===========================================================
Executes the walk-forward optimization protocol for SNDK.
"""
import logging
import math
import pandas as pd
import numpy as np
import copy

from src.otm_naked.sndk.config import SNDKLadderConfig
from src.otm_naked.sndk.signal_engine import SNDKLadderSignalEngine
from src.otm_naked.sndk.ladder_manager import LadderManager, LadderRung, _calc_friction
from src.otm_naked.sndk.optuna_optimizer import run_optuna_optimization
from src.otm_naked.strike_selector import bs_call_price, bs_put_price, bs_call_delta, bs_put_delta
from src.otm_naked.sndk.feature_engineering import _skew_adjusted_iv

logger = logging.getLogger(__name__)

def get_bs_price(S, K, T, r, sigma, opt="call"):
    return bs_call_price(S, K, T, r, sigma) if opt == "call" else bs_put_price(S, K, T, r, sigma)

def get_bs_delta(S, K, T, r, sigma, opt="call"):
    return bs_call_delta(S, K, T, r, sigma) if opt == "call" else bs_put_delta(S, K, T, r, sigma)


class SNDKBacktestEngine:
    def __init__(self, config: SNDKLadderConfig):
        self.config = config
        
    def create_labels(self, df: pd.DataFrame, dte_at_entry: int, profit_target: float) -> pd.DataFrame:
        """
        Generate ML target labels from historical entry days.
        """
        labels = []
        dates = []
        
        for i in range(len(df)):
            if i + 30 >= len(df):
                continue
            row = df.iloc[i]
            S = row["close"]
            iv = row["iv_est"]
            T = dte_at_entry / 365.0
            
            daily_move = row["daily_move_pct"]
            if abs(daily_move) < self.config.entry_trigger_pct:
                continue
                
            raw_opt = "call" if daily_move > 0 else "put"
            regime = str(row.get("regime", "SIDEWAYS"))
            if regime == "NO_TRADE":
                continue
            if regime in ("UPTREND", "EXTREME_UPTREND") and raw_opt == "call":
                continue  # Would have been blocked by signal engine
            if regime in ("DOWNTREND", "EXTREME_DOWNTREND") and raw_opt == "put":
                continue
            opt = raw_opt
            
            base_delta = getattr(self.config, 'delta_trending', 0.15) if regime in ("UPTREND", "DOWNTREND", "EXTREME_UPTREND", "EXTREME_DOWNTREND") else self.config.initial_delta
            
            iv_adj = _skew_adjusted_iv(iv, base_delta, option_type=opt)
            
            if opt == "put":
                from src.otm_naked.strike_selector import find_put_strike
                strike = find_put_strike(S, T, 0.045, iv_adj, target_delta=base_delta)
            else:
                from src.otm_naked.strike_selector import find_call_strike
                strike = find_call_strike(S, T, 0.045, iv_adj, target_delta=base_delta)
            
            entry_prem = get_bs_price(S, strike, T, 0.045, iv_adj, opt=opt)
            
            good = False
            for j in range(1, 31):
                if i + j >= len(df):
                    break
                future = df.iloc[i + j]
                S_future = future["close"]
                iv_future = future["iv_est"]
                T_remaining = max((dte_at_entry - j) / 365.0, 0.001)
                
                iv_future_adj = _skew_adjusted_iv(iv_future, base_delta, option_type=opt)
                current_prem = get_bs_price(S_future, strike, T_remaining, 0.045, iv_future_adj, opt=opt)
                if entry_prem > 0:
                    pnl_pct = (entry_prem - current_prem) / entry_prem
                    if pnl_pct >= profit_target:
                        good = True
                        break
                        
            labels.append(1 if good else 0)
            dates.append(df.iloc[i].name)
            
        return pd.DataFrame({"label": labels}, index=dates)

    def simulate_strategy(self, df: pd.DataFrame, use_ml: bool = True, ml_model=None, ml_features=None) -> list:
        ladder = LadderManager(self.config)
        signal_engine = SNDKLadderSignalEngine(self.config)
        
        trade_pnls = []
        current_nav = self.config.initial_capital  # Mark-to-market NAV (Fix #3 per Perplexity)
        
        for date, row in df.iterrows():
            S = float(row["close"])
            iv = float(row.get("iv_est", 0.3))
            
            # 1. Manage positions
            actions, pnl = ladder.manage_positions(date, S, iv)
            for action in actions:
                trade_pnls.append(action["pnl"])
                current_nav += action["pnl"]  # Mark NAV to market on each close
                
            # 2. Entry signal logic
            signal = signal_engine.evaluate(row, len(ladder.call_rungs), len(ladder.put_rungs))
            
            if not signal.should_enter:
                continue
                
            # ML filter
            ml_confidence = 1.0
            if use_ml and ml_model is not None and ml_features is not None:
                if date in ml_features.index:
                    feat_row = ml_features.loc[date]
                    ml_confidence = ml_model.predict_confidence(feat_row)
                    if ml_confidence < self.config.ml_confidence_min:
                        continue
                else:
                    continue
                    
            # Check portfolio delta limit
            current_port_delta = ladder.get_portfolio_delta(S, signal.target_dte / 365.0, iv)
            if abs(current_port_delta) > self.config.max_portfolio_delta:
                continue
                
            # Add rung
            regime = str(row.get("regime", "SIDEWAYS"))
            base_delta = getattr(self.config, 'delta_trending', 0.15) if regime in ("UPTREND", "DOWNTREND", "EXTREME_UPTREND", "EXTREME_DOWNTREND") else self.config.initial_delta
            rung_list_len = len(ladder.call_rungs) if signal.direction == "call" else len(ladder.put_rungs)
            target_delta = max(getattr(self.config, 'min_naked_delta', 0.15), base_delta - rung_list_len * self.config.ladder_delta_step)

            
            T_new = signal.target_dte / 365.0
            
            iv_adj = _skew_adjusted_iv(iv, target_delta, option_type=signal.direction)
            
            if signal.direction == "put":
                from src.otm_naked.strike_selector import find_put_strike
                strike = find_put_strike(S, T_new, 0.045, iv_adj, target_delta=target_delta)
            else:
                from src.otm_naked.strike_selector import find_call_strike
                strike = find_call_strike(S, T_new, 0.045, iv_adj, target_delta=target_delta)
                
            entry_prem = get_bs_price(S, strike, T_new, 0.045, iv_adj, opt=signal.direction)
            if entry_prem <= 0:
                continue
                
            # Sizing — dynamic NAV (Fix #3 per Perplexity: mark to market daily)
            nav = max(current_nav, self.config.initial_capital * 0.5)  # Floor at 50% to prevent over-leverage after drawdown
            max_risk = nav * self.config.position_size_pct
            margin_req = strike * 100 * 0.20 # Approximate naked margin
            contracts = max(1, int(max_risk / margin_req))
            
            new_rung = LadderRung(
                opt_type=signal.direction,
                strike=strike,
                entry_premium=entry_prem,
                entry_delta=abs(get_bs_delta(S, strike, T_new, 0.045, iv_adj, opt=signal.direction)),
                entry_iv=iv_adj,
                entry_date=date,
                rung_num=rung_list_len + 1,
                contracts=contracts,
                target_dte=signal.target_dte
            )
            
            # Spread conversion
            new_rung = ladder.convert_to_spread_if_needed(new_rung, ml_confidence, S, T_new, iv_adj)
            
            ladder.add_rung(new_rung)
            
        # Close remaining
        if len(df) > 0:
            last_date = df.index[-1]
            S = float(df.iloc[-1]["close"])
            iv = float(df.iloc[-1].get("iv_est", 0.3))
            
            for rung_list in [ladder.call_rungs, ladder.put_rungs]:
                for rung in rung_list:
                    days_held = (last_date - rung.entry_date).days
                    T_rem = max((rung.target_dte - days_held) / 365.0, 0.001)
                    iv_close_adj = _skew_adjusted_iv(iv, rung.entry_delta, option_type=rung.opt_type)
                    current_prem = get_bs_price(S, rung.strike, T_rem, 0.045, iv_close_adj, opt=rung.opt_type)
                    if rung.is_spread:
                        wing_prem = get_bs_price(S, rung.wing_strike, T_rem, 0.045, iv_close_adj, opt=rung.opt_type)
                        current_prem -= wing_prem
                        
                    pnl = (rung.entry_premium - current_prem) * rung.contracts * 100
                    
                    friction_cost = _calc_friction(rung.entry_premium, rung.entry_delta, rung.is_spread) * rung.contracts
                        
                    net_pnl = pnl - friction_cost
                    if rung.entry_premium * rung.contracts * 100 > 0:
                        trade_pnls.append(net_pnl)
                    
        return trade_pnls

    def walk_forward_backtest(self, df: pd.DataFrame, n_trials_optuna=100, window_train=126, window_test=63, step=63) -> tuple[pd.DataFrame, list]:
        all_results = []
        all_pnls = []
        
        i_start = 0
        window_num = 0
        
        base_config = copy.deepcopy(self.config)
        
        while i_start + window_train + window_test < len(df):
            i_train_end = i_start + window_train
            i_test_end  = i_train_end + window_test
            
            df_train = df.iloc[i_start:i_train_end]
            df_test  = df.iloc[i_train_end:i_test_end]
            
            logger.info(f"Walk-Forward Window {window_num+1} | Train: {df_train.index.min().date()} - {df_train.index.max().date()}")
            
            # 1. Optuna
            best_params = run_optuna_optimization(self, df_train, n_trials_optuna)
            for k, v in best_params.items():
                if hasattr(self.config, k):
                    setattr(self.config, k, v)
                
            # 2. ML Train — use ALL history up to the end of this train window
            # This accumulates signals over time: by window 4+ there are 30-60 labeled samples
            df_ml_history = df.iloc[0:i_train_end]  # Everything seen so far
            labels_df = self.create_labels(df_ml_history, self.config.dte_target, self.config.profit_take_pct)
            
            from src.otm_naked.entry_classifier import OTMNakedEntryClassifier
            ml_model = OTMNakedEntryClassifier()
            
            train_features = df_ml_history.loc[labels_df.index].copy()
            train_features["trade_won"] = labels_df["label"]
            # Only train ML if both classes (win/loss) are present
            n_classes = train_features["trade_won"].nunique()
            if n_classes < 2:
                logger.info(f"Window {window_num+1}: skipping ML (only {n_classes} class in labels — need wins AND losses)")
            else:
                try:
                    ml_model.fit(train_features, win_col="trade_won")
                except Exception as e:
                    logger.warning(f"Could not train ML for window {window_num+1}: {e}")
            
            # 3. Simulate
            pnls = self.simulate_strategy(df_test, use_ml=False, ml_model=None, ml_features=df_test)
            
            if pnls:
                pnl_series = pd.Series(pnls)
                win_rate = (pnl_series > 0).mean()
                sharpe = pnl_series.mean() / (pnl_series.std() + 1e-9) * math.sqrt(252) if pnl_series.std() > 0 else 0
                max_dd = (pnl_series.cumsum() - pnl_series.cumsum().cummax()).min()
                
                all_results.append({
                    "window": window_num + 1,
                    "test_start": df_test.index.min().date(),
                    "test_end": df_test.index.max().date(),
                    "n_trades": len(pnls),
                    "win_rate": round(win_rate * 100, 1),
                    "sharpe": round(sharpe, 3),
                    "best_params": best_params
                })
                
                all_pnls.extend(pnls)
                
            # Reset config
            self.config = copy.deepcopy(base_config)
            
            i_start += step
            window_num += 1
            
        return pd.DataFrame(all_results), all_pnls
