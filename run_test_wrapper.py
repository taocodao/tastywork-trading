import subprocess

try:
    print("Running scheduler flow test natively...")
    # Run the script and capture all output
    result = subprocess.run(
        [r"d:\Projects\tastywork-trading-1\.venv\Scripts\python.exe", "test_scheduler_flow.py"], 
        capture_output=True, 
        text=True, 
        check=True
    )
    print("STDOUT:")
    print(result.stdout)
except subprocess.CalledProcessError as e:
    print(f"COMMAND FAILED WITH CODE {e.returncode}")
    print("STDOUT:")
    print(e.stdout)
    print("STDERR:")
    print(e.stderr)
except Exception as e:
    print(f"UNEXPECTED ERROR: {e}")
