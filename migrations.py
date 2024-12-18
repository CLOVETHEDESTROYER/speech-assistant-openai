from sqlalchemy import create_engine
from sqlalchemy.sql import text
from app.config import DATABASE_URL


def migrate():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Add user_name column if it doesn't exist
        conn.execute(text("""
            ALTER TABLE call_schedules 
            ADD COLUMN user_name VARCHAR;
        """))
        conn.commit()


if __name__ == "__main__":
    migrate()
