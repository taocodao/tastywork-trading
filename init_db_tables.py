
import os
import sys
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.earnings_intelligence.database import init_db

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    print("Initializing database tables...")
    init_db()
    print("Database initialization complete.")
