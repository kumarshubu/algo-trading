import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL: str = os.getenv("DATABASE_URL", "")

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Supabase connected successfully")
except Exception as e:
    print(f"Connection failed: {e}")
finally:
    engine.dispose()
