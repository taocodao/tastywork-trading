import sys
import traceback

try:
    from main import CalendarSpreadsBot
    print("Import successful!")
except Exception as e:
    print("=" * 50)
    print("IMPORT ERROR:")
    print("=" * 50)
    traceback.print_exc()
    print(f"\nError: {e}")
