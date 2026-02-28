import sys
import py_compile
import traceback

try:
    py_compile.compile("d:/Projects/tastywork-trading-1/run_tqqq_scheduler.py", doraise=True)
    print("COMPILE OK")
except Exception as e:
    with open("compile_err.log", "w") as f:
        f.write(traceback.format_exc())
    print("COMPILE ERROR, saved to compile_err.log")
