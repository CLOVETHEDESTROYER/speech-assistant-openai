#!/usr/bin/env python3
"""
Database sequence fix script for conversations table.
This script resets the PostgreSQL sequence to fix duplicate key constraint violations.
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add the app directory to the path so we can import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.config import get_settings

def fix_conversations_sequence():
    """Fix the conversations table sequence by resetting it to the next available ID."""
    
    # Get database configuration
    settings = get_settings()
    database_url = settings.DATABASE_URL
    
    print(f"Connecting to database: {database_url.split('@')[1] if '@' in database_url else 'local'}")
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        # Test connection
        with engine.connect() as conn:
            print("✓ Database connection successful")
            
            # Check current sequence value
            result = conn.execute(text("SELECT currval('conversations_id_seq')"))
            current_seq = result.scalar()
            print(f"Current sequence value: {current_seq}")
            
            # Get max ID from conversations table
            result = conn.execute(text("SELECT MAX(id) FROM conversations"))
            max_id = result.scalar()
            print(f"Max conversation ID: {max_id}")
            
            if max_id is None:
                print("No conversations found, setting sequence to 1")
                next_seq = 1
            else:
                next_seq = max_id + 1
                print(f"Next sequence should be: {next_seq}")
            
            # Reset sequence
            conn.execute(text(f"SELECT setval('conversations_id_seq', {next_seq})"))
            conn.commit()
            
            # Verify the fix
            result = conn.execute(text("SELECT nextval('conversations_id_seq')"))
            new_seq = result.scalar()
            print(f"✓ Sequence reset successfully. Next ID will be: {new_seq}")
            
            # Test inserting a dummy record (will be rolled back)
            print("Testing sequence with dummy insert...")
            conn.execute(text("""
                INSERT INTO conversations (id, user_id, scenario, phone_number, direction, status, created_at)
                VALUES (nextval('conversations_id_seq'), 1, 'test', '1234567890', 'outbound', 'test', NOW())
            """))
            
            # Get the ID that was generated
            result = conn.execute(text("SELECT currval('conversations_id_seq')"))
            test_id = result.scalar()
            print(f"✓ Test insert successful with ID: {test_id}")
            
            # Rollback the test insert
            conn.rollback()
            print("✓ Test insert rolled back")
            
            print("\n🎉 Database sequence fixed successfully!")
            print(f"   Next conversation will use ID: {next_seq}")
            
    except Exception as e:
        print(f"❌ Error fixing sequence: {str(e)}")
        return False
    
    return True

if __name__ == "__main__":
    print("🔧 Fixing conversations table sequence...")
    print("=" * 50)
    
    success = fix_conversations_sequence()
    
    if success:
        print("\n✅ You can now try making calls again!")
        print("   The duplicate key constraint violation should be resolved.")
    else:
        print("\n❌ Failed to fix sequence. Check the error message above.")
        sys.exit(1)
