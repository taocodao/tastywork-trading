
import inspect
try:
    from tastytrade import Session
    print("Session imports OK")
    print(f"Signature: {inspect.signature(Session)}")
    print(f"Docstring: {Session.__doc__}")
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")
