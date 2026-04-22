
# Copy final files to output
import shutil, os
os.makedirs('/root/output', exist_ok=True)
shutil.copy('/root/qqq_pmcc_pseudocode_v2.txt', '/root/output/qqq_pmcc_pseudocode_v2.txt')
shutil.copy('/root/qqq_pmcc_backtest_v2.py', '/root/output/qqq_pmcc_backtest_v2.py')
shutil.copy('/root/qqq_pmcc_backtest_results.csv', '/root/output/qqq_pmcc_backtest_results.csv')
print("Files ready.")
