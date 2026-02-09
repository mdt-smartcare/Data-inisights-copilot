import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.sqliteDb.db import get_db_service

def dump_users():
    db = get_db_service()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, role FROM users")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    print("--- Users in DB ---")
    for u in users:
        print(f"User: {u['username']}, Role: '{u.get('role')}'")

if __name__ == "__main__":
    dump_users()
