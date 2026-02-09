
import sys
import os
import sqlite3
from unittest.mock import MagicMock, patch
from backend.sqliteDb.db import DatabaseService
import tempfile

def test_audit_trail():
    print("Testing Audit Trail Query...")
    
    # Create a temp file
    fd, temp_db_path = tempfile.mkstemp()
    os.close(fd)
    
    try:
        db = DatabaseService(temp_db_path)
        
        # Create test users
        db.create_user("alice", "pass1", "alice@test.com", "Alice Admin", "super_admin")
        db.create_user("bob", "pass2", "bob@test.com", "Bob Editor", "editor")
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Get IDs
        cursor.execute("SELECT id FROM users WHERE username='alice'")
        alice_id = cursor.fetchone()['id']
        cursor.execute("SELECT id FROM users WHERE username='bob'")
        bob_id = cursor.fetchone()['id']
        
        # Manually insert system prompts to simulate history
        # Prompt 1 by Alice
        cursor.execute("""
            INSERT INTO system_prompts (prompt_text, version, is_active, created_by)
            VALUES (?, ?, ?, ?)
        """, ("Prompt v1", 1, 0, str(alice_id)))
        
        # Prompt 2 by Bob
        cursor.execute("""
            INSERT INTO system_prompts (prompt_text, version, is_active, created_by)
            VALUES (?, ?, ?, ?)
        """, ("Prompt v2", 2, 1, str(bob_id)))
        
        conn.commit()
        conn.close()
        
        # Test get_all_prompts
        history = db.get_all_prompts()
        
        # Verify
        print(f"History items: {len(history)}")
        
        v2 = next(p for p in history if p['version'] == 2)
        v1 = next(p for p in history if p['version'] == 1)
        
        print(f"v2 created_by: {v2.get('created_by')}, created_by_username: {v2.get('created_by_username')}")
        print(f"v1 created_by: {v1.get('created_by')}, created_by_username: {v1.get('created_by_username')}")
        
        assert v2['created_by_username'] == 'bob'
        assert v1['created_by_username'] == 'alice'
        
        # Test get_active_config
        active = db.get_active_config()
        print(f"Active config version: {active['version']}, created_by_username: {active.get('created_by_username')}")
        
        assert active['version'] == 2
        assert active['created_by_username'] == 'bob'
        
        print("✅ Audit trail verification passed.")
    
    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

if __name__ == "__main__":
    test_audit_trail()
