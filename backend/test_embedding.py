import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(__file__))

from backend.api.routes.embedding_progress import _run_embedding_job
from backend.sqliteDb.db import get_db_service

async def main():
    try:
        # User ID doesn't matter much for logging
        await _run_embedding_job('emb-job-test-19', 19, 1)
        print("Job finished without raising out (check job status).")
        
        db = get_db_service()
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, error_message FROM embedding_jobs WHERE id = 'emb-job-test-19'")
        row = cursor.fetchone()
        if row:
            print(f"Status: {row['status']}, Error: {row['error_message']}")
        else:
            print("Job row not found.")
            
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
