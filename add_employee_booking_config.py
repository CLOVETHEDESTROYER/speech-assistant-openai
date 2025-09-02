#!/usr/bin/env python3
"""
Add employee-based booking configuration to UserBusinessConfig
"""

from app.config import DATABASE_URL
from sqlalchemy import create_engine, text
import os
import sys
sys.path.append('app')


def add_employee_booking_fields():
    """Add employee booking configuration fields to user_business_configs table"""

    # Get database URL
    database_url = DATABASE_URL
    engine = create_engine(database_url)

    # SQL to add new columns
    alter_sql = """
    ALTER TABLE user_business_configs 
    ADD COLUMN IF NOT EXISTS employee_count INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS max_concurrent_bookings INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS booking_policy VARCHAR(20) DEFAULT 'strict',
    ADD COLUMN IF NOT EXISTS allow_overbooking BOOLEAN DEFAULT FALSE;
    """

    try:
        with engine.connect() as conn:
            conn.execute(text(alter_sql))
            conn.commit()
            print("✅ Successfully added employee booking configuration fields")

            # Update existing records with default values
            update_sql = """
            UPDATE user_business_configs 
            SET employee_count = 1, 
                max_concurrent_bookings = 1, 
                booking_policy = 'strict',
                allow_overbooking = FALSE
            WHERE employee_count IS NULL;
            """
            conn.execute(text(update_sql))
            conn.commit()
            print("✅ Updated existing records with default values")

    except Exception as e:
        print(f"❌ Error adding employee booking fields: {e}")
        return False

    return True


if __name__ == "__main__":
    add_employee_booking_fields()
