import traceback
try:
    from src.tqqq.data_pipeline import TQQQDataPipeline
    import pandas as pd
    pd.set_option('display.max_columns', None)

    dp = TQQQDataPipeline()
    df = dp.get_ml_feature_dataframe(lookback_days=10)
    if df is not None and not df.empty:
        with open("dp_out.txt", "w") as f:
            f.write(str(df[['tqqq_close', 'rsi_2', 'rsi2_consec', 'hurst_100', 'ou_half_life', 'adx_14']].tail(3)))
    else:
        with open("dp_out.txt", "w") as f:
            f.write("DataFrame is empty or None")
except Exception as e:
    with open("dp_out.txt", "w") as f:
        f.write(traceback.format_exc())
