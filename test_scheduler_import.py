import traceback
import sys
import logging

logging.basicConfig(level=logging.INFO)

print("Starting import test...")

try:
    print("Importing run_tqqq_scheduler...")
    import run_tqqq_scheduler
    
    # Try to instantiate to ensure `__init__` code doesn't crash on config references
    print("Instantiating TQQQScheduler...")
    scheduler = run_tqqq_scheduler.TQQQScheduler(account_value=25000)
    
    result = "IMPORT OK\nINSTANTIATION OK"
    print(result)

except Exception as e:
    result = f"ERROR CAUGHT:\n{traceback.format_exc()}"
    print(result)

except SystemExit as e:
    result = f"SYSTEM EXIT CAUGHT: Code {e.code}"
    print(result)

# Write to file to guarantee we see it even if stdout is eaten by the terminal
with open("import_check_result.txt", "w", encoding="utf-8") as f:
    f.write(result)
    print("Wrote result to import_check_result.txt")
