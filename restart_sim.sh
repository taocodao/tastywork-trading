#!/bin/bash
pkill -f 'optuna_study|run_mc_backtest'
cd ~/tastywork-trading && git pull origin main
rm -f logs/mc_optimization.log mc_results/mc_production_run.json mc_window_*.db
mkdir -p ~/tastywork-trading/mc_results ~/tastywork-trading/logs

echo "Starting v2 NSGA-II optimization with 16 workers..."
PYTHONPATH=/home/ubuntu/tastywork-trading nohup python3 -m src.otm_naked.optimization.optuna_study \
    --start 2018-01-01 \
    --end 2025-12-31 \
    --n-trials 300 \
    --n-paths 100 \
    --n-jobs 16 \
    --is-days 756 \
    --oos-days 126 \
    --output mc_results/mc_production_run.json \
    >> logs/mc_optimization.log 2>&1 &

echo "Optimization PID: $!"
echo "Tailing log..."
sleep 5
tail -20 logs/mc_optimization.log
