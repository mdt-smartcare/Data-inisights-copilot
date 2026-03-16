"""
Schedule Manager Service - Database-backed management for Vector DB sync jobs.
This replaces APScheduler. It stores schedules in the database and calculates next_run_at using croniter.
Celery Beat will read this table to dispatch jobs.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum
from croniter import croniter

from backend.core.logging import get_logger
from backend.sqliteDb.db import get_db_service

logger = get_logger(__name__)


class ScheduleType(str, Enum):
    """Schedule frequency types."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    INTERVAL = "interval"
    CUSTOM = "custom"


class ScheduleStatus(str, Enum):
    """Status of last schedule run."""
    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"
    QUEUED = "queued"


class ScheduleManager:
    """
    Manages vector DB sync schedule configurations in SQLite.
    Computes exact `next_run_at` timestamps using cron expressions and croniter.
    """
    
    _instance: Optional['ScheduleManager'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if ScheduleManager._initialized:
            return
            
        self.db = get_db_service()
        self._ensure_table()
        
        ScheduleManager._initialized = True
        logger.info("ScheduleManager initialized")
    
    def _ensure_table(self):
        """Ensure the vector_db_schedules table exists."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS vector_db_schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vector_db_name TEXT NOT NULL UNIQUE,
                    enabled INTEGER DEFAULT 0,
                    schedule_type TEXT DEFAULT 'daily',
                    schedule_hour INTEGER DEFAULT 2,
                    schedule_minute INTEGER DEFAULT 0,
                    schedule_day_of_week INTEGER,
                    schedule_cron TEXT,
                    last_run_at TIMESTAMP,
                    next_run_at TIMESTAMP,
                    last_run_status TEXT,
                    last_run_job_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            ''')
            conn.commit()
        finally:
            conn.close()

    def _get_cron_string(
        self,
        schedule_type: ScheduleType,
        hour: int = 2,
        minute: int = 0,
        day_of_week: Optional[int] = None,
        cron_expression: Optional[str] = None
    ) -> str:
        """Convert UI schedule settings to a standard cron expression."""
        if schedule_type == ScheduleType.HOURLY:
            return f"{minute} * * * *"
        elif schedule_type == ScheduleType.INTERVAL:
            return f"*/{max(1, minute)} * * * *"
        elif schedule_type == ScheduleType.DAILY:
            return f"{minute} {hour} * * *"
        elif schedule_type == ScheduleType.WEEKLY:
            dow = day_of_week if day_of_week is not None else 0  # Default Monday (usually 1, but UI might send 0 for Sunday/Monday, translating directly)
            # Standard cron: 0=Sunday, 1=Monday... or 1-7
            # Typically UI uses 0=Sunday, 1=Monday. Let's pass it directly.
            return f"{minute} {hour} * * {dow}"
        elif schedule_type == ScheduleType.CUSTOM and cron_expression:
            return cron_expression
        else:
            return f"{minute} {hour} * * *"

    def calculate_next_run(self, cron_string: str, from_time: Optional[datetime] = None) -> Optional[datetime]:
        """Use croniter to calculate the next run time from a given cron string."""
        if not from_time:
            from_time = datetime.now(timezone.utc)
        
        try:
            itr = croniter(cron_string, from_time)
            next_run = itr.get_next(datetime)
            # Ensure timezone awareness
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=timezone.utc)
            return next_run
        except Exception as e:
            logger.error(f"Invalid cron string '{cron_string}': {e}")
            return None

    def create_schedule(
        self,
        vector_db_name: str,
        schedule_type: ScheduleType = ScheduleType.DAILY,
        hour: int = 2,
        minute: int = 0,
        day_of_week: Optional[int] = None,
        cron_expression: Optional[str] = None,
        enabled: bool = True,
        created_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create or update a schedule configuration.
        """
        cron_str = self._get_cron_string(schedule_type, hour, minute, day_of_week, cron_expression)
        next_run_at = self.calculate_next_run(cron_str) if enabled else None
        next_run_iso = next_run_at.isoformat() if next_run_at else None

        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO vector_db_schedules 
                    (vector_db_name, enabled, schedule_type, schedule_hour, 
                     schedule_minute, schedule_day_of_week, schedule_cron, 
                     next_run_at, created_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vector_db_name) DO UPDATE SET
                    enabled = excluded.enabled,
                    schedule_type = excluded.schedule_type,
                    schedule_hour = excluded.schedule_hour,
                    schedule_minute = excluded.schedule_minute,
                    schedule_day_of_week = excluded.schedule_day_of_week,
                    schedule_cron = excluded.schedule_cron,
                    next_run_at = excluded.next_run_at,
                    updated_at = excluded.updated_at
            ''', (
                vector_db_name, 1 if enabled else 0, schedule_type.value,
                hour, minute, day_of_week, cron_expression, next_run_iso, 
                created_by, datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()
            
            return self.get_schedule(vector_db_name)
            
        finally:
            conn.close()
    
    def get_schedule(self, vector_db_name: str) -> Optional[Dict[str, Any]]:
        """Get schedule configuration for a vector DB."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT * FROM vector_db_schedules WHERE vector_db_name = ?
            ''', (vector_db_name,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            schedule = dict(row)
            schedule['enabled'] = bool(schedule['enabled'])
            
            # Calculate dynamic countdown based on next_run_at
            if schedule.get('next_run_at') and schedule['enabled']:
                next_run = datetime.fromisoformat(schedule['next_run_at'])
                now = datetime.now(timezone.utc)
                delta = next_run - now
                schedule['countdown_seconds'] = max(0, int(delta.total_seconds()))
            else:
                schedule['countdown_seconds'] = None
            
            return schedule
            
        finally:
            conn.close()
    
    def delete_schedule(self, vector_db_name: str) -> bool:
        """Delete a schedule for a vector DB."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                DELETE FROM vector_db_schedules WHERE vector_db_name = ?
            ''', (vector_db_name,))
            conn.commit()
            
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted schedule for {vector_db_name}")
            
            return deleted
            
        finally:
            conn.close()
    
    def list_schedules(self) -> List[Dict[str, Any]]:
        """List all vector DB schedules."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT vector_db_name FROM vector_db_schedules')
            names = [row['vector_db_name'] for row in cursor.fetchall()]
            
            schedules = []
            for name in names:
                schedule = self.get_schedule(name)
                if schedule:
                    schedules.append(schedule)
            
            return schedules
            
        finally:
            conn.close()

    def update_run_status(self, vector_db_name: str, status: ScheduleStatus, job_id: Optional[str] = None):
        """Update last run status. Usually called by the Celery worker or Dispatcher."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            if status == ScheduleStatus.RUNNING or status == ScheduleStatus.QUEUED:
                cursor.execute('''
                    UPDATE vector_db_schedules 
                    SET last_run_status = ?, updated_at = ?
                    WHERE vector_db_name = ?
                ''', (status.value, now_str, vector_db_name))
            else:
                cursor.execute('''
                    UPDATE vector_db_schedules 
                    SET last_run_at = ?,
                        last_run_status = ?,
                        last_run_job_id = ?,
                        updated_at = ?
                    WHERE vector_db_name = ?
                ''', (now_str, status.value, job_id, now_str, vector_db_name))
            conn.commit()
        finally:
            conn.close()

    def update_next_run_time(self, vector_db_name: str, next_run: datetime):
        """Manually update the next run time. Usually called by the Dispatcher after queueing."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                UPDATE vector_db_schedules 
                SET next_run_at = ?, updated_at = ?
                WHERE vector_db_name = ?
            ''', (next_run.isoformat(), datetime.now(timezone.utc).isoformat(), vector_db_name))
            conn.commit()
        finally:
            conn.close()


# Singleton instance
_schedule_manager: Optional[ScheduleManager] = None


def get_schedule_manager() -> ScheduleManager:
    """Get or create the schedule manager singleton."""
    global _schedule_manager
    if _schedule_manager is None:
        _schedule_manager = ScheduleManager()
    return _schedule_manager
