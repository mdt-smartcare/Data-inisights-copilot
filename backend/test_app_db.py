import sqlite3
import os

db_path = os.path.abspath("sqliteDb/app.db")
print("app.db path:", db_path)
print("Stat:", oct(os.stat(db_path).st_mode))

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE document_index SET updated_at = CURRENT_TIMESTAMP WHERE id = 1")
    conn.commit()
    print("app.db update successful")
except Exception as e:
    import traceback
    traceback.print_exc()
