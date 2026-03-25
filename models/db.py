
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# Use PostgreSQL on EC2/prod (DATABASE_URL from .env), fallback to SQLite for local dev
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///data/trademind.db")

# PostgreSQL needs pool_pre_ping; SQLite needs check_same_thread
if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
