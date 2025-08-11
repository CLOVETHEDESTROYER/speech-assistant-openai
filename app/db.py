import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import QueuePool
from sqlalchemy import event
import logging
from sqlalchemy import text
from dotenv import load_dotenv

# Load environment variables from multiple possible locations
# Try production path first, then local paths
env_paths = [
    "/var/www/AiFriendChatBeta/.env",  # Production path
    ".env",                            # Local development
    "dev.env",                         # Development environment
    "test.env"                         # Test environment
]

for env_path in env_paths:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break

logger = logging.getLogger(__name__)

# Get database URL from environment, fallback to SQLite
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./sql_app.db"
)

if os.getenv("ENV", "production") == "production" and SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    raise RuntimeError(
        "DATABASE_URL points to SQLite in production. Set a Postgres DSN in .env.")

# Database configuration
DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "5"))
DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
DATABASE_POOL_TIMEOUT = int(os.getenv("DATABASE_POOL_TIMEOUT", "30"))
DATABASE_POOL_RECYCLE = int(os.getenv("DATABASE_POOL_RECYCLE", "3600"))

# Determine if we're using PostgreSQL
IS_POSTGRESQL = SQLALCHEMY_DATABASE_URL.startswith("postgresql")

if IS_POSTGRESQL:
    # PostgreSQL configuration with connection pooling
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        poolclass=QueuePool,
        pool_size=DATABASE_POOL_SIZE,
        max_overflow=DATABASE_MAX_OVERFLOW,
        pool_timeout=DATABASE_POOL_TIMEOUT,
        pool_recycle=DATABASE_POOL_RECYCLE,
        pool_pre_ping=True,  # Verify connections before use
        echo=os.getenv("DEBUG", "false").lower() == "true"
    )
    logger.info(
        f"Using PostgreSQL with connection pooling (pool_size={DATABASE_POOL_SIZE})")
else:
    # SQLite configuration (development)
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    logger.info("Using SQLite database (development mode)")

# Add connection event listeners for PostgreSQL
if IS_POSTGRESQL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        # Set PostgreSQL-specific connection settings
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET SESSION timezone = 'UTC'")
            # 30 seconds
            cursor.execute("SET SESSION statement_timeout = '30000'")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_sync():
    """Synchronous database session for non-async operations"""
    return SessionLocal()


def close_db_connections():
    """Close all database connections (useful for graceful shutdown)"""
    if IS_POSTGRESQL:
        engine.dispose()
        logger.info("PostgreSQL connections closed")
    else:
        logger.info("SQLite database - no connection pool to close")


def test_database_connection():
    """Test database connectivity"""
    try:
        with engine.connect() as connection:
            if IS_POSTGRESQL:
                result = connection.execute(text("SELECT version()"))
                version = result.scalar()
                logger.info(f"PostgreSQL connection successful: {version}")
            else:
                result = connection.execute(text("SELECT sqlite_version()"))
                version = result.scalar()
                logger.info(f"SQLite connection successful: {version}")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        return False
