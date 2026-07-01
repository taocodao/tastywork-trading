@echo off
setlocal EnableDelayedExpansion

:: =====================================================================
:: OTM Naked Monte Carlo Optimization & Backtest Pipeline (Local Windows)
:: =====================================================================
:: This script runs the full institutional-grade optimization locally,
:: utilizing all available CPU cores, and then immediately runs a 
:: historical backtest to verify the results.
:: =====================================================================

:: Move to the project root directory
cd /d "d:\Projects\tastywork-trading-1"

echo ==========================================================
echo   OTM Naked Monte Carlo Pipeline
echo   Starting at: %time%
echo ==========================================================
echo.

:: Ensure the results directory exists
if not exist "mc_results" mkdir "mc_results"

:: Set parameters for a full production run
set START_DATE=2018-01-01
set END_DATE=2025-12-31
set N_TRIALS=200
set N_PATHS=100
set N_JOBS=-1
set IS_DAYS=756
set OOS_DAYS=126
set RESULTS_FILE=mc_results\mc_local_run.json

echo [1/2] RUNNING MONTE CARLO OPTIMIZATION...
echo Using %N_TRIALS% trials, %N_PATHS% SBB paths per trial.
echo Parallelizing across all available CPU cores (N_JOBS=-1).
echo This will take approximately 1-2 hours depending on your CPU.
echo.

python -m src.otm_naked.optimization.optuna_study ^
    --start %START_DATE% ^
    --end %END_DATE% ^
    --n-trials %N_TRIALS% ^
    --n-paths %N_PATHS% ^
    --n-jobs %N_JOBS% ^
    --is-days %IS_DAYS% ^
    --oos-days %OOS_DAYS% ^
    --output %RESULTS_FILE%

:: Check if optimization succeeded
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Optimization failed or was interrupted.
    pause
    exit /b 1
)

if not exist "%RESULTS_FILE%" (
    echo.
    echo [ERROR] Results file %RESULTS_FILE% was not created.
    pause
    exit /b 1
)

echo.
echo [2/2] OPTIMIZATION COMPLETE. RUNNING BACKTEST...
echo Applying optimized parameters to the backtest engine...
echo.

python run_mc_backtest.py ^
    --results %RESULTS_FILE% ^
    --start %START_DATE% ^
    --end %END_DATE% ^
    --capital 50000 ^
    --no-ml

echo.
echo ==========================================================
echo   PIPELINE FINISHED at: %time%
echo   Optimization Results: %RESULTS_FILE%
echo   Trade Log: mc_results\mc_backtest_trades.csv
echo ==========================================================
pause
