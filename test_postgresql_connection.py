#!/usr/bin/env python3
"""
Test script to verify PostgreSQL connectivity
"""

import os
import sys

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from db import test_database_connection, IS_POSTGRESQL, SQLALCHEMY_DATABASE_URL

def main():
    print("🔍 Testing PostgreSQL Connection...")
    print(f"Database URL: {SQLALCHEMY_DATABASE_URL}")
    print(f"Using PostgreSQL: {IS_POSTGRESQL}")
    print()
    
    if test_database_connection():
        print("✅ Database connection successful!")
        print("🚀 Ready to run migrations")
    else:
        print("❌ Database connection failed!")
        print("Please check your PostgreSQL configuration")

if __name__ == "__main__":
    main()
