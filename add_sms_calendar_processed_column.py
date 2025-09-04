#!/usr/bin/env python3
"""
Database migration to add calendar_processed column to sms_messages table
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add the app directory to the Python path
sys.path.append('.')

# Import the existing database configuration
from app.db import SQLALCHEMY_DATABASE_URL

def run_migration():
    """Add calendar_processed column to sms_messages table"""
    try:
        # Create database engine using existing config
        engine = create_engine(SQLALCHEMY_DATABASE_URL)
        
        # Create session
        Session = sessionmaker(bind=engine)
        session = Session()
        
        print("🔄 Adding calendar_processed column to sms_messages table...")
        print(f"📊 Using database: {SQLALCHEMY_DATABASE_URL.split('@')[-1] if '@' in SQLALCHEMY_DATABASE_URL else SQLALCHEMY_DATABASE_URL}")
        
        # Add the calendar_processed column
        migration_sql = """
        ALTER TABLE sms_messages 
        ADD COLUMN IF NOT EXISTS calendar_processed BOOLEAN DEFAULT FALSE;
        """
        
        session.execute(text(migration_sql))
        session.commit()
        
        print("✅ Migration completed successfully!")
        
        # Verify the column was added
        result = session.execute(text("""
            SELECT column_name, data_type, column_default 
            FROM information_schema.columns 
            WHERE table_name = 'sms_messages' 
            AND column_name = 'calendar_processed';
        """))
        
        column = result.fetchone()
        if column:
            print(f"📋 New column added: {column[0]} ({column[1]}, default: {column[2]})")
        else:
            print("⚠️  Warning: Could not verify new column")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        session.rollback()
        session.close()
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
