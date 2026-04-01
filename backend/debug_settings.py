from backend.database.db import get_db_service
import json

try:
    db = get_db_service()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM system_settings WHERE category = 'ui' AND key = 'show_sql_query'")
    row = cursor.fetchone()
    print("SETTING_VALUE_START")
    print(json.dumps(dict(row) if row else {"error": "Not found"}, indent=2, default=str))
    print("SETTING_VALUE_END")
except Exception as e:
    print(f"Error: {e}")
