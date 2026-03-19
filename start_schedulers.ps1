Start-Process python -ArgumentList "run_turbocore_scheduler.py" -WindowStyle Hidden
Start-Process python -ArgumentList "run_turbocore_pro_scheduler.py" -WindowStyle Hidden
Write-Host "Started TurboCore & TurboCore Pro Schedulers in detached background processes."
