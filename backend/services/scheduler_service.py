"""
Scheduler Service - Native APScheduler integration for Vector DB sync jobs.
Provides background scheduling with real-time next_run_time exposure.
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

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


class SchedulerService:
    """
    Native scheduler service using APScheduler BackgroundScheduler.
    
    Manages scheduled vector DB sync jobs with:
    - Configurable schedule types (hourly, daily, weekly, custom cron)
    - Real-time next_run_time tracking
    - Persistent schedule configuration in SQLite
    - Integration with embedding job service
    """
    
    _instance: Optional['SchedulerService'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if SchedulerService._initialized:
            return
            
        self.db = get_db_service()
        self._ensure_table()
        
        # Configure APScheduler
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': ThreadPoolExecutor(max_workers=3)
        }
        job_defaults = {
            'coalesce': True,  # Combine missed executions into one
            'max_instances': 1,  # Prevent overlapping runs
            'misfire_grace_time': 3600  # Allow 1 hour grace period for misfires
        }
        
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults
        )
        
        SchedulerService._initialized = True
        logger.info("SchedulerService initialized")
    
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
    
    def start(self):
        """Start the scheduler and load all enabled schedules."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("APScheduler started")
            
            # Load and register all enabled schedules from database
            self._load_schedules_from_db()
    
    def shutdown(self):
        """Gracefully shutdown the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("APScheduler shutdown complete")
    
    def _load_schedules_from_db(self):
        """Load all enabled schedules from database and register with APScheduler."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT vector_db_name, schedule_type, schedule_hour, schedule_minute,
                       schedule_day_of_week, schedule_cron
                FROM vector_db_schedules
                WHERE enabled = 1
            ''')
            rows = cursor.fetchall()
            
            for row in rows:
                self._register_job(
                    vector_db_name=row['vector_db_name'],
                    schedule_type=ScheduleType(row['schedule_type']),
                    hour=row['schedule_hour'],
                    minute=row['schedule_minute'],
                    day_of_week=row['schedule_day_of_week'],
                    cron_expression=row['schedule_cron']
                )
            
            logger.info(f"Loaded {len(rows)} scheduled jobs from database")
            
        finally:
            conn.close()
    
    def _get_trigger(
        self,
        schedule_type: ScheduleType,
        hour: int = 2,
        minute: int = 0,
        day_of_week: Optional[int] = None,
        cron_expression: Optional[str] = None
    ):
        """Create appropriate APScheduler trigger based on schedule type."""
        if schedule_type == ScheduleType.HOURLY:
            return CronTrigger(minute=minute)
        elif schedule_type == ScheduleType.INTERVAL:
            # Use minute as the interval in minutes
            return IntervalTrigger(minutes=max(1, minute))
        elif schedule_type == ScheduleType.DAILY:
            return CronTrigger(hour=hour, minute=minute)
        elif schedule_type == ScheduleType.WEEKLY:
            dow = day_of_week if day_of_week is not None else 0  # Default Monday
            return CronTrigger(day_of_week=dow, hour=hour, minute=minute)
        elif schedule_type == ScheduleType.CUSTOM and cron_expression:
            return CronTrigger.from_crontab(cron_expression)
        else:
            # Default to daily at 2 AM
            return CronTrigger(hour=2, minute=0)
    
    def _register_job(
        self,
        vector_db_name: str,
        schedule_type: ScheduleType,
        hour: int = 2,
        minute: int = 0,
        day_of_week: Optional[int] = None,
        cron_expression: Optional[str] = None
    ):
        """Register a job with APScheduler."""
        job_id = f"sync_{vector_db_name}"
        
        # Remove existing job if present
        existing_job = self.scheduler.get_job(job_id)
        if existing_job:
            self.scheduler.remove_job(job_id)
        
        trigger = self._get_trigger(
            schedule_type, hour, minute, day_of_week, cron_expression
        )
        
        self.scheduler.add_job(
            func=self._execute_sync_job,
            trigger=trigger,
            id=job_id,
            args=[vector_db_name],
            name=f"Vector DB Sync: {vector_db_name}",
            replace_existing=True
        )
        
        # Update next_run_at in database
        job = self.scheduler.get_job(job_id)
        next_run = getattr(job, 'next_run_time', None)
        if job and next_run:
            self._update_next_run_time(vector_db_name, next_run)
        
        logger.info(f"Registered scheduled job for {vector_db_name}: {schedule_type.value}")
    
    def _execute_sync_job(self, vector_db_name: str, is_manual: bool = False):
        """Execute the vector DB sync job."""
        job_source = "manual" if is_manual else "scheduled"
        logger.info(f"Executing {job_source} sync for vector DB: {vector_db_name}")
        
        # Update status to running
        self._update_run_status(vector_db_name, ScheduleStatus.RUNNING)
        
        try:
            # Find the config associated with this vector DB
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT sp.id as prompt_id, pc.embedding_config 
                FROM system_prompts sp
                JOIN prompt_configs pc ON sp.id = pc.prompt_id
                WHERE sp.is_active = 1
                ORDER BY sp.id DESC
            ''')
            rows = cursor.fetchall()
            conn.close()
            
            config_id = None
            for row in rows:
                try:
                    import json
                    emb_conf = json.loads(row['embedding_config'] or '{}')
                    if emb_conf.get('vectorDbName') == vector_db_name:
                        config_id = row['prompt_id']
                        break
                except Exception:
                    continue
            
            if not config_id:
                raise ValueError(f"No active configuration found for vector DB: {vector_db_name}")
            
            # Trigger embedding job using the existing service
            from backend.services.embedding_job_service import get_embedding_job_service
            from backend.models.schemas import User
            
            job_service = get_embedding_job_service()
            
            # Create a system user for scheduled jobs
            system_user = User(
                id=0,
                username="scheduler",
                email="scheduler@system",
                role="super_admin",
                is_active=True
            )
            
            # Create job (we'll run it synchronously in a new event loop)
            job_id = job_service.create_job(
                config_id=config_id,
                total_documents=100,  # Placeholder, will be updated
                user=system_user,
                batch_size=50,
                max_concurrent=5
            )
            
            # Run the embedding job
            from backend.api.routes.embedding_progress import _run_embedding_job
            
            # Create new event loop for async execution in thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    _run_embedding_job(
                        job_id=job_id,
                        config_id=config_id,
                        user_id=0,
                        incremental=True
                    )
                )
            finally:
                loop.close()
            
            # Update status
            self._update_run_status(
                vector_db_name, 
                ScheduleStatus.SUCCESS, 
                job_id=job_id
            )
            logger.info(f"{job_source.capitalize()} sync completed for {vector_db_name}, job_id={job_id}")
            
        except Exception as e:
            logger.error(f"Scheduled sync failed for {vector_db_name}: {e}")
            self._update_run_status(vector_db_name, ScheduleStatus.FAILED)
        
        # Update next run time after execution
        job = self.scheduler.get_job(f"sync_{vector_db_name}")
        next_run = getattr(job, 'next_run_time', None)
        if job and next_run:
            self._update_next_run_time(vector_db_name, next_run)
    
    def _update_next_run_time(self, vector_db_name: str, next_run: datetime):
        """Update the next_run_at timestamp in database."""
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
    
    def _update_run_status(
        self, 
        vector_db_name: str, 
        status: ScheduleStatus,
        job_id: Optional[str] = None
    ):
        """Update the last run status in database."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        try:
            if status == ScheduleStatus.RUNNING:
                now_str = datetime.now(timezone.utc).isoformat()
                cursor.execute('''
                    UPDATE vector_db_schedules 
                    SET last_run_status = ?, updated_at = ?
                    WHERE vector_db_name = ?
                ''', (status.value, now_str, vector_db_name))
            else:
                now_str = datetime.now(timezone.utc).isoformat()
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
        Create or update a schedule for a vector DB.
        
        Args:
            vector_db_name: Name of the vector database
            schedule_type: Type of schedule (hourly, daily, weekly, custom)
            hour: Hour of day (0-23) for daily/weekly schedules
            minute: Minute (0-59)
            day_of_week: Day of week (0=Monday, 6=Sunday) for weekly
            cron_expression: Custom cron expression for custom type
            enabled: Whether schedule is active
            created_by: Username creating the schedule
            
        Returns:
            Schedule configuration dict with next_run_time
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Upsert schedule
            cursor.execute('''
                INSERT INTO vector_db_schedules 
                    (vector_db_name, enabled, schedule_type, schedule_hour, 
                     schedule_minute, schedule_day_of_week, schedule_cron, created_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vector_db_name) DO UPDATE SET
                    enabled = excluded.enabled,
                    schedule_type = excluded.schedule_type,
                    schedule_hour = excluded.schedule_hour,
                    schedule_minute = excluded.schedule_minute,
                    schedule_day_of_week = excluded.schedule_day_of_week,
                    schedule_cron = excluded.schedule_cron,
                    updated_at = excluded.updated_at
            ''', (
                vector_db_name, 1 if enabled else 0, schedule_type.value,
                hour, minute, day_of_week, cron_expression, created_by, datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()
            
            # Register or remove job based on enabled status
            job_id = f"sync_{vector_db_name}"
            if enabled:
                self._register_job(
                    vector_db_name, schedule_type, hour, minute,
                    day_of_week, cron_expression
                )
            else:
                existing_job = self.scheduler.get_job(job_id)
                if existing_job:
                    self.scheduler.remove_job(job_id)
            
            # Get the schedule info to return
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
            
            # Get real-time next_run_time from APScheduler
            job = self.scheduler.get_job(f"sync_{vector_db_name}")
            next_run = getattr(job, 'next_run_time', None)
            if job and next_run:
                schedule['next_run_at'] = next_run.isoformat()
                # Calculate countdown in seconds using local time
                now = datetime.now(next_run.tzinfo)
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
            # Remove from APScheduler
            job_id = f"sync_{vector_db_name}"
            existing_job = self.scheduler.get_job(job_id)
            if existing_job:
                self.scheduler.remove_job(job_id)
            
            # Remove from database
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
    
    def trigger_now(self, vector_db_name: str) -> str:
        """Manually trigger an immediate sync for a vector DB."""
        job_id = f"sync_{vector_db_name}"
        
        # Check if schedule exists
        schedule = self.get_schedule(vector_db_name)
        if not schedule:
            raise ValueError(f"No schedule found for vector DB: {vector_db_name}")
        
        # Execute immediately in background
        self.scheduler.add_job(
            func=self._execute_sync_job,
            args=[vector_db_name, True],  # True for is_manual
            id=f"{job_id}_manual_{datetime.now().timestamp()}",
            name=f"Manual Sync: {vector_db_name}"
        )
        
        logger.info(f"Triggered manual sync for {vector_db_name}")
        return f"Manual sync triggered for {vector_db_name}"


# Singleton instance
_scheduler_service: Optional[SchedulerService] = None


def get_scheduler_service() -> SchedulerService:
    """Get or create the scheduler service singleton."""
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
