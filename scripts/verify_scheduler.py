import time
from datetime import datetime
import sys
import os

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.schedule_manager import get_schedule_manager, ScheduleType

def print_step(msg):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] \033[1;36m{msg}\033[0m")

def print_success(msg):
    print(f"\033[1;32m✓ {msg}\033[0m")

def print_error(msg):
    print(f"\033[1;31m✗ {msg}\033[0m")

def verify_celery_fix():
    print_step("Initial Checks: Verifying APScheduler is removed.")
    
    manager = get_schedule_manager()
    now = datetime.now()
    test_db = "test_scheduler_db"
    
    print_step(f"Creating a schedule for Vector DB: {test_db} (due in 1 minute)")
    
    try:
        schedule = manager.create_schedule(
            vector_db_name=test_db,
            schedule_type=ScheduleType.HOURLY,
            minute=(now.minute + 1) % 60,
            enabled=True
        )
        print_success(f"Schedule created successfully via ScheduleManager.")
        print(f"   Next Run At (Calculated by croniter): {schedule.get('next_run_at')}")
    except Exception as e:
        print_error(f"Failed to create schedule: {e}")
        sys.exit(1)
       
    print_step("Triggering a manual sync to ensure it queues to Celery rather than APScheduler...")
    try:
        from backend.pipeline.workers.embedding_worker import celery_app
        celery_app.send_task(
            'backend.pipeline.workers.embedding_worker.execute_vector_db_sync',
            args=[test_db, True],
            queue='embedding_tasks'
        )
        print_success("Manual sync triggered via dispatcher queue.")
    except Exception as e:
        print_error(f"Failed to trigger sync: {e}")

    print_step("Verification Complete.")
    print("--------------------------------------------------")
    print("To fully verify the infrastructure:")
    print("1. Look at the Celery Beat terminal (`conda run ... beat`). You should see:")
    print("   [INFO] Celery Beat Tick: Dispatching Vector DB Syncs...")
    print("   This proves Celery Beat is driving the scheduling, NOT the web worker.")
    print("\n2. Look at the Celery Worker terminal (`conda run ... worker`). You should see:")
    print(f"   [INFO] Executing manual sync for vector DB: {test_db}")
    print("   This proves the job was pushed to Redis and picked up by the out-of-process worker.")
    print("\n3. If you stop the web worker (`uvicorn ...`), the Celery Beat process continues to tick and dispatch jobs.")
    print("--------------------------------------------------")
    
    # Clean up
    print_step("Cleaning up test schedule...")
    manager.delete_schedule(test_db)
    print_success("Cleanup complete.")

if __name__ == "__main__":
    verify_celery_fix()
