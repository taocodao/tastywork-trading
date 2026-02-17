
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from models.db import engine, Base
from models.user import User
from models.zebra_position import ZebraPosition

def init_db():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")
    
if __name__ == "__main__":
    init_db()
