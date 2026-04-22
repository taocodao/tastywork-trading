
# Fix the smooth_regime function and re-run
fix = '''
def smooth_regime(regime_series: pd.Series, window: int = 5) -> pd.Series:
    """Rolling mode on string regime labels — encode as int, mode, decode back."""
    encoding = {
        "BULL_STRONG": 4,
        "BULL_MODERATE": 3,
        "CHOPPY": 2,
        "BEAR": 1,
        "BEAR_SMA_FORCED": 0,
    }
    decoding = {v: k for k, v in encoding.items()}
    encoded = regime_series.map(encoding).astype(float)
    smoothed = encoded.rolling(window, min_periods=1).apply(
        lambda x: pd.Series(x).mode()[0], raw=True
    )
    return smoothed.map(lambda v: decoding.get(int(v), "CHOPPY"))
'''

# Patch and rewrite the file with the fix
with open('/root/qqq_pmcc_backtest_v2.py', 'r') as f:
    content = f.read()

old_fn = '''def smooth_regime(regime_series: pd.Series, window: int = 5) -> pd.Series:
    """Rolling mode to prevent single-day flip-flops (5-day smoothing)."""
    return regime_series.rolling(window, min_periods=1).apply(
        lambda x: pd.Series(x).mode()[0], raw=False
    )'''

new_fn = '''def smooth_regime(regime_series: pd.Series, window: int = 5) -> pd.Series:
    """Rolling mode to prevent single-day flip-flops (5-day smoothing)."""
    encoding = {"BULL_STRONG": 4, "BULL_MODERATE": 3, "CHOPPY": 2, "BEAR": 1, "BEAR_SMA_FORCED": 0}
    decoding  = {v: k for k, v in encoding.items()}
    encoded   = regime_series.map(encoding).astype(float)
    smoothed  = encoded.rolling(window, min_periods=1).apply(
        lambda x: pd.Series(x).mode()[0], raw=True
    )
    return smoothed.map(lambda v: decoding.get(int(v), "CHOPPY"))'''

content = content.replace(old_fn, new_fn)
with open('/root/qqq_pmcc_backtest_v2.py', 'w') as f:
    f.write(content)

result = subprocess.run(["python3", "/root/qqq_pmcc_backtest_v2.py"],
                        capture_output=True, text=True, timeout=120)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr[-1500:] if result.stderr else "")
