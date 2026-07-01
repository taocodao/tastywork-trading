"""Diagnostic: isolate what changed between Phase 1 and Phase 2 for each year."""
import sys
sys.path.insert(0, ".")
from src.otm_naked.config import OTMNakedConfig
from src.otm_naked.backtest_engine import OTMNakedBacktestEngine
from backtest_otm_naked import download_data

for year in [2018, 2020, 2022, 2024]:
    start = f"{year}-01-01"
    end   = f"{year}-12-31"

    price_data, vix, vix3m, rf = download_data([], start, end)

    # Phase 1 config (pathway_b OFF, RSI sort disabled by reverting sort_score)
    cfg_off = OTMNakedConfig(backtest_start=start, backtest_end=end, pathway_b_enabled=False)
    eng_off = OTMNakedBacktestEngine(cfg_off)
    r_off   = eng_off.run(price_data, vix, vix3m, rf, initial_capital=50000, use_ml=False)
    m_off   = r_off["metrics"]
    t_off   = r_off["trades"]

    # Phase 2 config (pathway_b ON)
    cfg_on = OTMNakedConfig(backtest_start=start, backtest_end=end, pathway_b_enabled=True)
    eng_on = OTMNakedBacktestEngine(cfg_on)
    r_on   = eng_on.run(price_data, vix, vix3m, rf, initial_capital=50000, use_ml=False)
    m_on   = r_on["metrics"]
    t_on   = r_on["trades"]

    a_cnt = (t_on["pathway"] == "A").sum() if "pathway" in t_on.columns else len(t_on)
    b_cnt = (t_on["pathway"] == "B").sum() if "pathway" in t_on.columns else 0
    b_wr  = t_on[t_on["pathway"] == "B"]["trade_won"].mean() * 100 if b_cnt > 0 else 0

    print(f"{year}: P1={m_off['cagr_pct']:.1f}% ({len(t_off)} trades) | "
          f"P2={m_on['cagr_pct']:.1f}% ({a_cnt}A+{b_cnt}B) "
          f"B_WR={b_wr:.0f}%  DD={m_on['max_drawdown_pct']:.1f}%")
    print(f"      RSI sort: did A-trades change? {len(t_off)} -> {a_cnt} (delta {a_cnt-len(t_off)})")
