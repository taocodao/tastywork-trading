import sys
try:
    with open('import_log.txt', 'w') as log:
        log.write("Starting imports...\n")
        
        from http.server import HTTPServer, BaseHTTPRequestHandler
        log.write("http.server ok\n")
        
        import json
        import os
        import uuid
        from datetime import datetime, timedelta
        from dotenv import load_dotenv
        log.write("std libs ok\n")
        
        try:
            from tastytrade import Session, Account
            log.write("tastytrade ok\n")
        except ImportError as e:
            log.write(f"tastytrade failed: {e}\n")
            raise
            
        try:
            from tastytrade.instruments import Option, get_option_chain
            log.write("tastytrade.instruments ok\n")
        except ImportError as e:
            log.write(f"tastytrade.instruments failed: {e}\n")
            raise

        try:
            import pandas as pd
            log.write("pandas ok\n")
        except ImportError as e:
            log.write(f"pandas failed: {e}\n")
            raise

        try:
            from src.zebra.client import ZebraClient
            log.write("ZebraClient import ok\n")
        except ImportError as e:
            log.write(f"ZebraClient failed: {e}\n")
            # Don't raise, just log
            
        try:
            from src.zebra.construction_engine import ZebraConstructionEngine
            log.write("ZebraConstructionEngine import ok\n")
        except ImportError as e:
            log.write(f"ZebraConstructionEngine failed: {e}\n")

        log.write("All imports done.\n")
        
    with open('import_success.txt', 'w') as f:
        f.write("Success")
        
except Exception as e:
    with open('import_failed.txt', 'w') as f:
        f.write(str(e))
