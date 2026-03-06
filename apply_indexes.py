
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def main():
    env_path = '/home/ubuntu/tastywork-trading/.env'
    if not os.path.exists(env_path):
        print(f"Error: {env_path} not found")
        return

    load_dotenv(env_path)
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        db_url = os.getenv("DB_URL")
    
    if not db_url:
        print("Error: DATABASE_URL not found in .env")
        return

    print(f"Connecting to database...")
    engine = create_engine(db_url)

    try:
        with engine.connect() as conn:
            print("Adding signals(created_at) index...")
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_signals_created_at ON signals (created_at DESC);"))
            
            print("Adding user_signal_executions(created_at) index...")
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_signal_executions_created_at ON user_signal_executions (created_at DESC);"))
            
            print("Adding positions(created_at) index...")
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_positions_created_at ON positions (created_at DESC);"))
            
            conn.commit()
            print("Successfully added indexes!")
    except Exception as e:
        print(f"Error applying indexes: {e}")

if __name__ == "__main__":
    main()
