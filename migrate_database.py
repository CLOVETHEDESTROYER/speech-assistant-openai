#!/usr/bin/env python3
"""
Database migration script for AiFriendChat backend
This script updates the existing database to include the new schema changes
"""

import os
import sys
import sqlite3
from datetime import datetime

def run_migration():
    """Run database migration to update schema"""
    
    # Database file path
    db_path = "sql_app.db"
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return False
    
    # Create backup
    backup_path = f"sql_app.db.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"Created backup: {backup_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if users table needs name column
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'name' not in columns:
            print("Adding 'name' column to users table...")
            cursor.execute("ALTER TABLE users ADD COLUMN name VARCHAR")
            
        if 'created_at' not in columns:
            print("Adding 'created_at' column to users table...")
            cursor.execute("ALTER TABLE users ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
            
        # Check if tokens table needs updates
        cursor.execute("PRAGMA table_info(tokens)")
        token_columns = [column[1] for column in cursor.fetchall()]
        
        # Check if token field exists (old schema)
        if 'token' in token_columns and 'access_token' not in token_columns:
            print("Updating tokens table schema...")
            # Rename token to access_token
            cursor.execute("""
                CREATE TABLE tokens_new (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    access_token VARCHAR UNIQUE NOT NULL,
                    token_type VARCHAR DEFAULT 'bearer',
                    refresh_token VARCHAR UNIQUE NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users (id)
                )
            """)
            
            # Copy existing data, generating dummy refresh tokens
            cursor.execute("""
                INSERT INTO tokens_new (id, user_id, access_token, token_type, refresh_token, created_at)
                SELECT id, user_id, token, 'bearer', 'refresh_' || token, created_at
                FROM tokens
            """)
            
            # Drop old table and rename new one
            cursor.execute("DROP TABLE tokens")
            cursor.execute("ALTER TABLE tokens_new RENAME TO tokens")
            cursor.execute("CREATE INDEX ix_tokens_id ON tokens (id)")
            
        elif 'access_token' not in token_columns:
            print("Adding missing columns to tokens table...")
            cursor.execute("ALTER TABLE tokens ADD COLUMN access_token VARCHAR UNIQUE")
            cursor.execute("ALTER TABLE tokens ADD COLUMN token_type VARCHAR DEFAULT 'bearer'")
            cursor.execute("ALTER TABLE tokens ADD COLUMN refresh_token VARCHAR UNIQUE")
            
        # Check if usage_limits table exists and has all required columns
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='usage_limits'")
        if not cursor.fetchone():
            print("Creating usage_limits table...")
            cursor.execute("""
                CREATE TABLE usage_limits (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE,
                    app_type VARCHAR(15) NOT NULL DEFAULT 'mobile',
                    calls_made_today INTEGER DEFAULT 0,
                    calls_made_this_week INTEGER DEFAULT 0,
                    calls_made_this_month INTEGER DEFAULT 0,
                    calls_made_total INTEGER DEFAULT 0,
                    last_call_date DATE,
                    week_start_date DATE DEFAULT CURRENT_TIMESTAMP,
                    month_start_date DATE DEFAULT CURRENT_TIMESTAMP,
                    trial_calls_remaining INTEGER DEFAULT 2,
                    trial_calls_used INTEGER DEFAULT 0,
                    trial_start_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    trial_end_date DATETIME,
                    is_trial_active BOOLEAN DEFAULT 1,
                    subscription_tier VARCHAR(21),
                    is_subscribed BOOLEAN DEFAULT 0,
                    subscription_start_date DATETIME,
                    subscription_end_date DATETIME,
                    subscription_status VARCHAR,
                    weekly_call_limit INTEGER,
                    monthly_call_limit INTEGER,
                    billing_cycle VARCHAR,
                    last_payment_date DATETIME,
                    next_payment_date DATETIME,
                    app_store_transaction_id VARCHAR,
                    app_store_product_id VARCHAR,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users (id)
                )
            """)
            cursor.execute("CREATE INDEX ix_usage_limits_id ON usage_limits (id)")
            
            # Initialize usage limits for existing users
            cursor.execute("SELECT id FROM users")
            users = cursor.fetchall()
            for (user_id,) in users:
                cursor.execute("""
                    INSERT INTO usage_limits 
                    (user_id, app_type, trial_calls_remaining, is_trial_active, is_subscribed)
                    VALUES (?, 'mobile', 2, 1, 0)
                """, (user_id,))
            
            print(f"Initialized usage limits for {len(users)} existing users")
        
        conn.commit()
        print("Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()

if __name__ == "__main__":
    print("Starting database migration...")
    success = run_migration()
    if success:
        print("Migration completed successfully!")
        sys.exit(0)
    else:
        print("Migration failed!")
        sys.exit(1) 